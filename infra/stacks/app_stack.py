"""
Main application stack: data plane + app plane in a single stack.

Consolidated for Phase 1 to avoid cross-stack dependency cycles
(bucket grants + KMS key policies + SG ingress rules cross-refer
between former DataStack and AppStack).
"""

from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_apigatewayv2 as apigw2
from aws_cdk import aws_apigatewayv2_integrations as apigw2_integ
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as cf_origins
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_events
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import aws_sqs as sqs
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parents[2]


class AppStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id_: str,
        *,
        stage_name: str,
        custom_domain: str | None = None,
        custom_domain_certificate: acm.ICertificate | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id_, **kwargs)

        self.stage_name = stage_name
        # When both are present we put a CloudFront distribution in
        # front of the SPA + API so the browser can talk to one origin
        # over HTTPS at the user's own hostname. Both must be supplied
        # together; passing one without the other is a wiring bug and
        # we fail fast rather than silently degrade.
        if (custom_domain is None) != (custom_domain_certificate is None):
            raise ValueError(
                "AppStack: custom_domain and custom_domain_certificate "
                "must be provided together (got "
                f"domain={custom_domain!r}, cert={custom_domain_certificate!r})"
            )
        self.custom_domain = custom_domain
        self.custom_domain_certificate = custom_domain_certificate
        self.use_custom_domain = custom_domain is not None

        # ---- Data plane ----
        self.key = kms.Key(
            self,
            "DataKey",
            alias=f"alias/slideforge-{stage_name}-data",
            enable_key_rotation=True,
            removal_policy=cdk.RemovalPolicy.RETAIN if stage_name == "prod" else cdk.RemovalPolicy.DESTROY,
        )

        self.artifacts_bucket = s3.Bucket(
            self,
            "ArtifactsBucket",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            cors=[
                # Allow browser PUTs against presigned URLs (template upload)
                # and GETs when the user opens a preview URL from the SPA.
                # Phase 1 uses "*" for origin since the web bucket name is
                # only known after first deploy; Phase 2 should lock this
                # down to the exact CloudFront/website origin.
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.HEAD,
                    ],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    exposed_headers=["ETag"],
                    max_age=3000,
                ),
            ],
            enforce_ssl=True,
            versioned=stage_name == "prod",
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="intelligent-tiering",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                            transition_after=cdk.Duration.days(30),
                        )
                    ],
                )
            ],
            removal_policy=cdk.RemovalPolicy.RETAIN if stage_name == "prod" else cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=stage_name != "prod",
        )

        # Static website hosting for the Next.js SPA. Public-read, no
        # CloudFront in Phase 1 (documented trade-off — HTTP only for
        # internal use; Phase 2 adds CloudFront + HTTPS). No explicit
        # bucket_name — CDK generates a unique one per deploy so we
        # don't get "bucket already exists" from stray retained buckets
        # left behind by earlier failed stacks.
        #
        # Private vs public is driven by use_custom_domain: when off,
        # we keep the legacy public S3 website (browser hits
        # http://...s3-website-... directly). When on, the bucket goes
        # fully private and CloudFront's OAC serves it over HTTPS at
        # the user's domain.
        if self.use_custom_domain:
            self.web_bucket = s3.Bucket(
                self,
                "WebBucket",
                # Private; OAC grants CloudFront read.
                public_read_access=False,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                # Static website hosting is unnecessary with CloudFront —
                # the distribution handles the index document and SPA
                # 404→index fallback for client routing.
                removal_policy=cdk.RemovalPolicy.DESTROY,
                auto_delete_objects=True,
            )
        else:
            self.web_bucket = s3.Bucket(
                self,
                "WebBucket",
                website_index_document="index.html",
                website_error_document="index.html",
                public_read_access=True,
                block_public_access=s3.BlockPublicAccess(
                    block_public_acls=False,
                    block_public_policy=False,
                    ignore_public_acls=False,
                    restrict_public_buckets=False,
                ),
                removal_policy=cdk.RemovalPolicy.DESTROY,
                auto_delete_objects=True,
            )

        # Why a NAT Gateway here:
        #
        # The API Lambda lives in the VPC so it can reach RDS. It also has
        # to call out to:
        #   - secretsmanager.ap-northeast-1.amazonaws.com (DB creds, Anthropic key)
        #   - api.anthropic.com (Claude)
        #   - cognito-idp.ap-northeast-1.amazonaws.com (JWKS)
        #   - sqs/s3/kms regional endpoints
        #
        # PRIVATE_ISOLATED subnets have no default route, so every external
        # call hangs until Lambda times out. One NAT Gateway in a single AZ
        # gives the API Lambda internet egress. Costs ~3,500 JPY/month,
        # which we absorb as a Phase 1 trade-off for actually being able to
        # call Claude.
        #
        # Subnet plan (non-destructive upgrade from the original isolated-only
        # layout): keep `isolated` so RDS doesn't have to move (data stays),
        # ADD `private` (PRIVATE_WITH_EGRESS) on fresh CIDR slots for the
        # Lambda to live in. Without keeping isolated, CDK would try to give
        # the new private subnets the same CIDRs as the existing isolated
        # ones (10.0.2.0/24, 10.0.3.0/24) and CFN aborts with
        # "The CIDR ... conflicts with another subnet".
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            availability_zones=["ap-northeast-1a", "ap-northeast-1c"],
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        rds_sg = ec2.SecurityGroup(
            self,
            "RdsSg",
            vpc=self.vpc,
            description="RDS SG",
            allow_all_outbound=False,
        )
        lambda_sg = ec2.SecurityGroup(
            self,
            "LambdaSg",
            vpc=self.vpc,
            description="Lambda SG",
            allow_all_outbound=True,
        )
        rds_sg.add_ingress_rule(
            peer=lambda_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow Lambda to RDS",
        )

        self.db_secret = sm.Secret(
            self,
            "DbSecret",
            secret_name=f"slideforge/{stage_name}/db",
            description="SlideForge RDS credentials",
            encryption_key=self.key,
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"username": "slideforge"}',
                generate_string_key="password",
                exclude_characters='"@/\\',
                password_length=24,
            ),
        )

        self.db = rds.DatabaseInstance(
            self,
            "Db",
            # PostgresEngineVersion.of() lets us pick an exact supported
            # minor version without being limited to whatever the installed
            # CDK's named enum happens to include. AWS deprecates minor
            # versions over time, so pinning to e.g. VER_16_3 will start
            # failing with "Cannot find version 16.3 for postgres" once
            # AWS drops it. 16.6 is the current long-term-supported 16.x
            # at time of writing.
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.of("16.6", "16"),
            ),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.SMALL),
            vpc=self.vpc,
            # Keep RDS in the existing isolated subnet so the in-place CFN
            # update doesn't try to recreate it (would also lose the data).
            # RDS doesn't need internet anyway.
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[rds_sg],
            multi_az=False,
            allocated_storage=20,
            max_allocated_storage=50,
            storage_encryption_key=self.key,
            credentials=rds.Credentials.from_secret(self.db_secret),
            backup_retention=cdk.Duration.days(7 if stage_name == "prod" else 1),
            # deletion_protection=False for Phase 1 so CFN can freely recreate
            # the instance when VPC / subnet config changes (the pipeline's
            # stuck-stack auto-cleanup also depends on being able to delete).
            # Phase 2 flips this back on — at that point we have real data
            # that needs guarding.
            deletion_protection=False,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Shared Anthropic API key (populated during bootstrap, referenced by
        # all stages in Phase 1). Split per-stage in Phase 2 if needed.
        anthropic_secret = sm.Secret.from_secret_name_v2(
            self, "AnthropicApiKey", "slideforge/anthropic"
        )

        # ---- Application plane ----
        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=f"slideforge-{stage_name}",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_digits=True,
                require_symbols=True,
                require_lowercase=True,
                require_uppercase=True,
            ),
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True),
            removal_policy=cdk.RemovalPolicy.RETAIN if stage_name == "prod" else cdk.RemovalPolicy.DESTROY,
        )
        self.user_pool_client = self.user_pool.add_client(
            "WebClient",
            user_pool_client_name=f"slideforge-{stage_name}-web",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True, user_password=False),
            prevent_user_existence_errors=True,
        )

        # ---- Machine-to-machine auth for external integrations ----
        #
        # External services (e.g. report_bot on Cloud Run) call
        # /api/v1/external/slides using the OAuth 2.0 client_credentials
        # grant. That requires:
        #   1. A resource server with a custom scope. The access token's
        #      `scope` claim then carries "<resource_server_id>/<scope>".
        #   2. A user pool domain so the token endpoint
        #      (https://<domain>/oauth2/token) is reachable.
        #   3. An app client with generate_secret=True and the
        #      client_credentials flow enabled.
        self.api_resource_server = self.user_pool.add_resource_server(
            "ApiResourceServer",
            identifier="slideforge-api",
            scopes=[
                cognito.ResourceServerScope(
                    scope_name="slides:create",
                    scope_description="Create slides via the external integration API",
                ),
            ],
        )
        slides_create_scope = cognito.OAuthScope.resource_server(
            self.api_resource_server,
            cognito.ResourceServerScope(
                scope_name="slides:create",
                scope_description="Create slides via the external integration API",
            ),
        )
        self.m2m_client = self.user_pool.add_client(
            "M2MClient",
            user_pool_client_name=f"slideforge-{stage_name}-m2m",
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=False,
                    implicit_code_grant=False,
                    client_credentials=True,
                ),
                scopes=[slides_create_scope],
            ),
            # client_credentials tokens never represent a human, so the
            # standard user-existence-error toggle is irrelevant.
            prevent_user_existence_errors=True,
        )
        # Token endpoint lives at https://<prefix>.auth.<region>.amazoncognito.com.
        # Prefix must be globally unique within the region; account id
        # keeps it stable across re-deploys without colliding with
        # other tenants.
        self.user_pool_domain = self.user_pool.add_domain(
            "UserPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"slideforge-{stage_name}-{self.account}",
            ),
        )
        # Stash the M2M client_secret in Secrets Manager so the consumer
        # (Cloud Run / report_bot) can fetch it via a stable ARN instead
        # of running `aws cognito-idp describe-user-pool-client` by hand.
        # SecretsManager doesn't enforce JSON, but storing as JSON makes
        # it easy to consume with the standard
        # SecretsManager.get_secret_value -> json.loads pattern.
        self.m2m_credentials_secret = sm.Secret(
            self,
            "M2MCredentials",
            secret_name=f"slideforge/{stage_name}/m2m-credentials",
            description=(
                "Cognito client_credentials grant: client_id + client_secret "
                "for external services calling /api/v1/external/slides"
            ),
            encryption_key=self.key,
            secret_object_value={
                "client_id": cdk.SecretValue.unsafe_plain_text(
                    self.m2m_client.user_pool_client_id
                ),
                "client_secret": self.m2m_client.user_pool_client_secret,
                "token_url": cdk.SecretValue.unsafe_plain_text(
                    f"https://slideforge-{stage_name}-{self.account}"
                    f".auth.{self.region}.amazoncognito.com/oauth2/token"
                ),
                "scope": cdk.SecretValue.unsafe_plain_text(
                    "slideforge-api/slides:create"
                ),
            },
        )

        render_dlq = sqs.Queue(
            self,
            "RenderDlq",
            queue_name=f"slideforge-{stage_name}-render-dlq",
            retention_period=cdk.Duration.days(14),
        )
        self.render_queue = sqs.Queue(
            self,
            "RenderQueue",
            queue_name=f"slideforge-{stage_name}-render",
            visibility_timeout=cdk.Duration.minutes(10),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=render_dlq),
        )

        # Blueprint queue: async LLM-call jobs enqueued by the API Lambda
        # and processed by the blueprint_worker Lambda. Sits alongside
        # RenderQueue so the ~30s Claude call doesn't run inside the
        # 30-second HTTP API integration window.
        blueprint_dlq = sqs.Queue(
            self,
            "BlueprintDlq",
            queue_name=f"slideforge-{stage_name}-blueprint-dlq",
            retention_period=cdk.Duration.days(14),
        )
        self.blueprint_queue = sqs.Queue(
            self,
            "BlueprintQueue",
            queue_name=f"slideforge-{stage_name}-blueprint",
            # Visibility timeout must be >= worker Lambda timeout (5 min)
            # to avoid a second delivery while the first is still
            # legitimately running. Padded a bit for safety.
            visibility_timeout=cdk.Duration.minutes(6),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=2, queue=blueprint_dlq),
        )

        # Revision queue: same idea as blueprint_queue but for the
        # /revise endpoint. Inline /revise used to run the LLM call on
        # the request thread which routinely tripped API Gateway's 29s
        # integration timeout while the Lambda kept committing in the
        # background — clients saw 503/400/500 cascades. Moving it
        # off-thread fixes that and gives the worker a 5-minute budget.
        revision_dlq = sqs.Queue(
            self,
            "RevisionDlq",
            queue_name=f"slideforge-{stage_name}-revision-dlq",
            retention_period=cdk.Duration.days(14),
        )
        self.revision_queue = sqs.Queue(
            self,
            "RevisionQueue",
            queue_name=f"slideforge-{stage_name}-revision",
            visibility_timeout=cdk.Duration.minutes(6),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=2, queue=revision_dlq),
        )

        # Render Lambda needs DB access so it can flip
        # ProjectRow.status to "complete"/"failed" when a job finishes —
        # otherwise the UI has no way to know when to enable the
        # preview/.pptx/.pdf buttons. Putting it in the same private
        # subnets as the API Lambda + sharing lambda_sg gives it RDS
        # access (already allowed by RdsSg ingress rule above).
        self.render_function = lambda_.DockerImageFunction(
            self,
            "RenderFunction",
            function_name=f"slideforge-{stage_name}-render",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=str(REPO_ROOT / "app" / "render"),
            ),
            memory_size=3008,
            # Bumped from 5 → 10 min to accommodate the layout-designer
            # LLM path. Calls are parallelized in-handler but Claude
            # tail latency + retry storms still occasionally cross 5
            # min when the deck is large or rate-limited. 10 min is
            # still well under the 15 min Lambda hard cap.
            timeout=cdk.Duration.minutes(10),
            ephemeral_storage_size=cdk.Size.gibibytes(2),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_sg],
            environment={
                "ENV": stage_name,
                "LOG_LEVEL": "INFO",
                "S3_BUCKET": self.artifacts_bucket.bucket_name,
                "DB_SECRET_ARN": self.db_secret.secret_arn,
                "DB_ENDPOINT": self.db.instance_endpoint.hostname,
                # Phase 2 render quality: slot-aware layout (strips body
                # placeholders even for text-only / section-divider slides,
                # so "本文 / 図解 / 表をここに配置" stops bleeding through)
                # + theme color inheritance (pulls palette from the uploaded
                # template's theme.xml instead of always using DEFAULT_PALETTE).
                "FF_SLOT_RENDER": "1",
                "FF_THEME_INHERITANCE": "1",
                # Phase 3: per-slide layout designer LLM. When on, each
                # slide's body area is composed by Claude from the
                # LayoutSpec primitive vocabulary instead of the
                # generic figure_renderer presets. The render Lambda
                # falls back to the deterministic path automatically
                # if the LLM call or validation fails.
                "FF_LAYOUT_DESIGNER": "1",
                "ANTHROPIC_API_KEY_SECRET": anthropic_secret.secret_name,
            },
        )
        self.artifacts_bucket.grant_read_write(self.render_function)
        anthropic_secret.grant_read(self.render_function)
        self.db_secret.grant_read(self.render_function)
        self.render_function.add_event_source(
            lambda_events.SqsEventSource(self.render_queue, batch_size=1)
        )

        api_role = iam.Role(
            self,
            "ApiRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )
        self.artifacts_bucket.grant_read_write(api_role)
        self.db_secret.grant_read(api_role)
        anthropic_secret.grant_read(api_role)
        self.render_queue.grant_send_messages(api_role)
        self.blueprint_queue.grant_send_messages(api_role)
        self.revision_queue.grant_send_messages(api_role)

        self.api_function = lambda_.Function(
            self,
            "ApiFunction",
            function_name=f"slideforge-{stage_name}-api",
            runtime=lambda_.Runtime.PYTHON_3_12,
            # Bundle the source under /asset-output/api/ (keeping the
            # package name) and load the handler as `api.main.handler`.
            # If we drop main.py at the root instead, Lambda imports it
            # as a top-level module, and main.py's `from .config import
            # ...` relative imports fail with ImportModuleError because
            # a top-level module has no parent package.
            #
            # Also bundle `render/` at the package root because api code
            # transitively imports `render.figure_renderers` (for the
            # dynamic LLM prompt catalog) and `render.slot_extractor`
            # (for template analysis / lazy slot migration). Omitting
            # it makes Lambda init crash with ModuleNotFoundError and
            # API Gateway returns `{"message":"Internal Server Error"}`
            # for every request.
            handler="api.main.handler",
            code=lambda_.Code.from_asset(
                str(REPO_ROOT / "app"),
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir -r api/requirements.txt -t /asset-output "
                        "&& mkdir -p /asset-output/api /asset-output/render "
                        "&& cp -r api/. /asset-output/api/ "
                        "&& cp -r render/. /asset-output/render/",
                    ],
                ),
            ),
            memory_size=1024,
            timeout=cdk.Duration.seconds(60),
            role=api_role,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_sg],
            environment={
                "ENV": stage_name,
                "S3_BUCKET": self.artifacts_bucket.bucket_name,
                "DB_SECRET_ARN": self.db_secret.secret_arn,
                "DB_ENDPOINT": self.db.instance_endpoint.hostname,
                "RENDER_QUEUE_URL": self.render_queue.queue_url,
                "BLUEPRINT_QUEUE_URL": self.blueprint_queue.queue_url,
                "REVISION_QUEUE_URL": self.revision_queue.queue_url,
                # Phase 2 blueprint quality: require headline_message on
                # every SlideSpec. Must match the worker's setting so
                # blueprints written with a placeholder also load back.
                "FF_HEADLINE_REQUIRED": "1",
                "COGNITO_USER_POOL_ID": self.user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": self.user_pool_client.user_pool_client_id,
                # The M2M client id is accepted as an alternative `client_id`
                # claim by app/api/auth/cognito.py — that's how the API
                # tells a user request apart from a client_credentials call
                # from an external service. Required scope is enforced in
                # the external router, not here.
                "COGNITO_M2M_CLIENT_ID": self.m2m_client.user_pool_client_id,
                "EXTERNAL_API_REQUIRED_SCOPE": "slideforge-api/slides:create",
                "ANTHROPIC_API_KEY_SECRET": anthropic_secret.secret_name,
            },
        )

        # Blueprint worker Lambda: shares the api/ source asset (same
        # bundling, same deps) but runs with a different handler and an
        # SQS trigger. Split from the HTTP API Lambda so it can have a
        # 5-minute timeout for the LLM call without giving API requests
        # the same ceiling, and so worker crashes don't poison the HTTP
        # container's warm pool.
        blueprint_worker_role = iam.Role(
            self,
            "BlueprintWorkerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )
        self.db_secret.grant_read(blueprint_worker_role)
        anthropic_secret.grant_read(blueprint_worker_role)
        self.blueprint_queue.grant_consume_messages(blueprint_worker_role)
        # External-API path: after the worker writes the blueprint, it
        # auto-enqueues the render job (msg.auto_render=True). Without
        # this grant the send_message call would 403 and the project
        # would sit in status="rendering" forever from the polling
        # client's perspective.
        self.render_queue.grant_send_messages(blueprint_worker_role)

        self.blueprint_worker_function = lambda_.Function(
            self,
            "BlueprintWorkerFunction",
            function_name=f"slideforge-{stage_name}-blueprint-worker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.blueprint_worker.handler",
            # Share the same bundle layout as the API Lambda (api/ + render/
            # at the package root). The worker loads `api.services.llm`,
            # which pulls in `api.prompts.builder` -> `render.figure_renderers`
            # at import time.
            code=lambda_.Code.from_asset(
                str(REPO_ROOT / "app"),
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir -r api/requirements.txt -t /asset-output "
                        "&& mkdir -p /asset-output/api /asset-output/render "
                        "&& cp -r api/. /asset-output/api/ "
                        "&& cp -r render/. /asset-output/render/",
                    ],
                ),
            ),
            memory_size=1024,
            timeout=cdk.Duration.minutes(5),
            role=blueprint_worker_role,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_sg],
            environment={
                "ENV": stage_name,
                "S3_BUCKET": self.artifacts_bucket.bucket_name,
                "DB_SECRET_ARN": self.db_secret.secret_arn,
                "DB_ENDPOINT": self.db.instance_endpoint.hostname,
                # Used when the SQS message carries auto_render=True
                # (external integration API). Same queue the HTTP /render
                # endpoint feeds, so the downstream render Lambda doesn't
                # have to care who enqueued the job.
                "RENDER_QUEUE_URL": self.render_queue.queue_url,
                # Cognito not needed — worker is invoked by SQS, never
                # handles a user token directly.
                "ANTHROPIC_API_KEY_SECRET": anthropic_secret.secret_name,
                # Phase 2 blueprint quality: inject the dynamic figure-type
                # catalog (with per-figure input_schema_example) into the
                # LLM system prompt instead of the static .txt fallback.
                "FF_DYNAMIC_PROMPT_CATALOG": "1",
                # Headline-message enforcement (Pydantic + sanitizer).
                # Must match the API Lambda's setting so blueprints written
                # here deserialize cleanly when read back via GET.
                "FF_HEADLINE_REQUIRED": "1",
            },
        )
        self.blueprint_worker_function.add_event_source(
            lambda_events.SqsEventSource(self.blueprint_queue, batch_size=1)
        )

        # Revision worker Lambda. Same code bundle as the API +
        # blueprint workers (api/ + render/ at the package root); only
        # the handler entry point and SQS source differ.
        revision_worker_role = iam.Role(
            self,
            "RevisionWorkerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )
        self.db_secret.grant_read(revision_worker_role)
        anthropic_secret.grant_read(revision_worker_role)
        self.revision_queue.grant_consume_messages(revision_worker_role)

        self.revision_worker_function = lambda_.Function(
            self,
            "RevisionWorkerFunction",
            function_name=f"slideforge-{stage_name}-revision-worker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.revision_worker.handler",
            code=lambda_.Code.from_asset(
                str(REPO_ROOT / "app"),
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir -r api/requirements.txt -t /asset-output "
                        "&& mkdir -p /asset-output/api /asset-output/render "
                        "&& cp -r api/. /asset-output/api/ "
                        "&& cp -r render/. /asset-output/render/",
                    ],
                ),
            ),
            memory_size=1024,
            timeout=cdk.Duration.minutes(5),
            role=revision_worker_role,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_sg],
            environment={
                "ENV": stage_name,
                "S3_BUCKET": self.artifacts_bucket.bucket_name,
                "DB_SECRET_ARN": self.db_secret.secret_arn,
                "DB_ENDPOINT": self.db.instance_endpoint.hostname,
                "ANTHROPIC_API_KEY_SECRET": anthropic_secret.secret_name,
                # Same flag set as the API + blueprint workers so a
                # blueprint mutated here deserializes cleanly when the
                # API Lambda reads it back.
                "FF_HEADLINE_REQUIRED": "1",
            },
        )
        self.revision_worker_function.add_event_source(
            lambda_events.SqsEventSource(self.revision_queue, batch_size=1)
        )

        # CORS handled at the API Gateway level, not the Lambda. Two reasons:
        #   1. API Gateway answers OPTIONS preflight directly without
        #      invoking Lambda. When the Lambda is warming up, unable to
        #      reach a dependency, or in trouble for any other reason, CORS
        #      preflight still succeeds and the browser gets a useful error
        #      on the *real* request instead of a generic "TypeError: Load
        #      failed" from a failed preflight.
        #   2. Single source of CORS headers: no risk of duplicate
        #      `Access-Control-Allow-Origin` (which browsers reject).
        self.http_api = apigw2.HttpApi(
            self,
            "HttpApi",
            api_name=f"slideforge-{stage_name}",
            cors_preflight=apigw2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigw2.CorsHttpMethod.ANY],
                allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
                max_age=cdk.Duration.hours(1),
            ),
        )
        # Explicitly list methods and *exclude* OPTIONS. If OPTIONS is part
        # of the route (e.g. via HttpMethod.ANY), the explicit route takes
        # precedence over the API-level cors_preflight above, so preflight
        # OPTIONS gets forwarded to the Lambda. FastAPI has no OPTIONS
        # handler (CORSMiddleware is deliberately off), so it 405s and the
        # browser reports "preflight doesn't have HTTP ok status".
        # Leaving OPTIONS off lets API Gateway answer preflight directly.
        self.http_api.add_routes(
            path="/{proxy+}",
            methods=[
                apigw2.HttpMethod.GET,
                apigw2.HttpMethod.POST,
                apigw2.HttpMethod.PUT,
                apigw2.HttpMethod.PATCH,
                apigw2.HttpMethod.DELETE,
                apigw2.HttpMethod.HEAD,
            ],
            integration=apigw2_integ.HttpLambdaIntegration(
                "ApiIntegration",
                handler=self.api_function,
                # 29s is the CDK-enforced upper bound (AWS docs say the
                # hard ceiling is 30s, but CDK validates <= 29s on
                # synth). Bumped from the default because some requests
                # still run close to the limit; anything longer moved
                # to the async blueprint worker pattern.
                timeout=cdk.Duration.seconds(29),
            ),
        )

        # ---- Observability (formerly a separate stack) ----
        cw.Alarm(
            self,
            "ApiErrors",
            metric=self.api_function.metric_errors(period=cdk.Duration.minutes(5)),
            threshold=5,
            evaluation_periods=3,
            alarm_description=f"API Lambda errors ({stage_name})",
        )
        cw.Alarm(
            self,
            "RenderFailures",
            metric=self.render_function.metric_errors(period=cdk.Duration.minutes(5)),
            threshold=3,
            evaluation_periods=3,
            alarm_description=f"Render Lambda errors ({stage_name})",
        )
        cw.Alarm(
            self,
            "ApiDuration",
            metric=self.api_function.metric_duration(period=cdk.Duration.minutes(5)),
            threshold=5000,
            evaluation_periods=3,
            alarm_description=f"API p95 duration > 5s ({stage_name})",
        )
        dashboard = cw.Dashboard(
            self,
            "SlideForgeDashboard",
            dashboard_name=f"SlideForge-{stage_name}",
        )
        dashboard.add_widgets(
            cw.GraphWidget(
                title="API Invocations / Errors",
                left=[self.api_function.metric_invocations(), self.api_function.metric_errors()],
                width=12,
            ),
            cw.GraphWidget(
                title="Render Invocations / Errors",
                left=[self.render_function.metric_invocations(), self.render_function.metric_errors()],
                width=12,
            ),
            cw.GraphWidget(
                title="API Duration (ms)",
                left=[self.api_function.metric_duration()],
                width=12,
            ),
        )

        # ---- CloudFront (only when a custom domain is configured) ----
        #
        # Two origins under one HTTPS distribution so the browser sees
        # everything as same-origin: that kills CORS as a moving part
        # and lets the SPA hit /api/* without preflight OPTIONS.
        #
        # Default behavior:  S3 (private, OAC) → SPA static files
        # /api/* behavior:   API Gateway HTTP API → FastAPI Lambda
        #
        # If/when the custom domain is removed, deploy reverts to the
        # legacy public S3 website branch above.
        self.distribution: cloudfront.Distribution | None = None
        if self.use_custom_domain:
            assert self.custom_domain is not None
            assert self.custom_domain_certificate is not None

            api_origin = cf_origins.HttpOrigin(
                # `api_endpoint` is e.g. https://abc.execute-api.<region>.amazonaws.com
                # — strip the scheme + trailing slash for the origin host.
                cdk.Fn.select(2, cdk.Fn.split("/", self.http_api.api_endpoint)),
                protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
            )

            api_behavior = cloudfront.BehaviorOptions(
                origin=api_origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                # Anything mutating goes through here (POST /revise,
                # PATCH /blueprint, etc.), so allow the full method set.
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                # API responses must never be cached: every request is
                # tenant-scoped and most are dynamic. Forward everything
                # to the origin verbatim.
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
            )

            web_origin = cf_origins.S3BucketOrigin.with_origin_access_control(
                self.web_bucket,
            )

            # Next.js static export emits per-route index.html files
            # (`/projects/index.html`, `/templates/index.html`, …).
            # S3 in REST/OAC mode doesn't auto-resolve "/projects/" to
            # "/projects/index.html" the way the website endpoint
            # would, so without rewriting the path the request returns
            # 403 and CloudFront's SPA fallback hands the visitor
            # /index.html (the dashboard). Rewriting at the viewer-
            # request stage lets S3 see the real key.
            spa_uri_rewrite = cloudfront.Function(
                self,
                "SpaUriRewrite",
                code=cloudfront.FunctionCode.from_inline(
                    """
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith('/')) {
    request.uri = uri + 'index.html';
  } else if (uri.split('/').pop().indexOf('.') === -1) {
    // No file extension in the last segment — treat as a route and
    // resolve to its index.html (matches Next.js trailingSlash:true
    // export layout).
    request.uri = uri + '/index.html';
  }
  return request;
}
"""
                ),
                runtime=cloudfront.FunctionRuntime.JS_2_0,
            )

            self.distribution = cloudfront.Distribution(
                self,
                "WebDistribution",
                domain_names=[self.custom_domain],
                certificate=self.custom_domain_certificate,
                default_root_object="index.html",
                default_behavior=cloudfront.BehaviorOptions(
                    origin=web_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                    compress=True,
                    function_associations=[
                        cloudfront.FunctionAssociation(
                            function=spa_uri_rewrite,
                            event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                        ),
                    ],
                ),
                additional_behaviors={
                    "/api/*": api_behavior,
                },
                # Next.js static export emits per-route HTML files; a
                # client-side route refresh hits a missing key when the
                # browser asks for /projects/list/. Map 403/404 from S3
                # back to /index.html so the SPA's router takes over.
                error_responses=[
                    cloudfront.ErrorResponse(
                        http_status=403,
                        response_http_status=200,
                        response_page_path="/index.html",
                        ttl=cdk.Duration.seconds(0),
                    ),
                    cloudfront.ErrorResponse(
                        http_status=404,
                        response_http_status=200,
                        response_page_path="/index.html",
                        ttl=cdk.Duration.seconds(0),
                    ),
                ],
                price_class=cloudfront.PriceClass.PRICE_CLASS_200,
                comment=f"SlideForge {stage_name} ({self.custom_domain})",
            )

        cdk.CfnOutput(self, "ApiEndpoint", value=self.http_api.api_endpoint)
        cdk.CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        cdk.CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        cdk.CfnOutput(
            self,
            "M2MClientId",
            value=self.m2m_client.user_pool_client_id,
            description="Cognito app client id for the external integration API.",
        )
        cdk.CfnOutput(
            self,
            "M2MCredentialsSecretArn",
            value=self.m2m_credentials_secret.secret_arn,
            description=(
                "Secrets Manager secret containing client_id / client_secret / "
                "token_url / scope for client_credentials access to "
                "/api/v1/external/slides."
            ),
        )
        cdk.CfnOutput(
            self,
            "CognitoTokenUrl",
            value=(
                f"https://slideforge-{stage_name}-{self.account}"
                f".auth.{self.region}.amazoncognito.com/oauth2/token"
            ),
            description="OAuth 2.0 token endpoint for the client_credentials grant.",
        )
        cdk.CfnOutput(self, "ArtifactsBucketName", value=self.artifacts_bucket.bucket_name)
        cdk.CfnOutput(self, "RenderQueueUrl", value=self.render_queue.queue_url)
        cdk.CfnOutput(self, "WebBucketName", value=self.web_bucket.bucket_name)
        if self.distribution is not None:
            assert self.custom_domain is not None
            cdk.CfnOutput(
                self,
                "WebsiteUrl",
                value=f"https://{self.custom_domain}",
            )
            cdk.CfnOutput(
                self,
                "DistributionDomainName",
                value=self.distribution.distribution_domain_name,
                description=(
                    "Add a CNAME from the custom domain to this value on "
                    "the parent DNS host (スターサーバー)."
                ),
            )
            cdk.CfnOutput(
                self,
                "DistributionId",
                value=self.distribution.distribution_id,
                description="Used by the deploy pipeline to invalidate the SPA cache.",
            )
        else:
            cdk.CfnOutput(
                self,
                "WebsiteUrl",
                value=f"http://{self.web_bucket.bucket_website_domain_name}",
            )
