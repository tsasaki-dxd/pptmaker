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
    def __init__(self, scope: Construct, id_: str, *, stage_name: str, **kwargs) -> None:
        super().__init__(scope, id_, **kwargs)

        self.stage_name = stage_name

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

        self.render_function = lambda_.DockerImageFunction(
            self,
            "RenderFunction",
            function_name=f"slideforge-{stage_name}-render",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=str(REPO_ROOT / "app" / "render"),
            ),
            memory_size=3008,
            timeout=cdk.Duration.minutes(5),
            ephemeral_storage_size=cdk.Size.gibibytes(2),
            environment={
                "ENV": stage_name,
                "LOG_LEVEL": "INFO",
                "S3_BUCKET": self.artifacts_bucket.bucket_name,
            },
        )
        self.artifacts_bucket.grant_read_write(self.render_function)
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
            handler="api.main.handler",
            code=lambda_.Code.from_asset(
                str(REPO_ROOT / "app" / "api"),
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir -r requirements.txt -t /asset-output "
                        "&& mkdir -p /asset-output/api "
                        "&& cp -r . /asset-output/api/",
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
                "COGNITO_USER_POOL_ID": self.user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": self.user_pool_client.user_pool_client_id,
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

        self.blueprint_worker_function = lambda_.Function(
            self,
            "BlueprintWorkerFunction",
            function_name=f"slideforge-{stage_name}-blueprint-worker",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="api.blueprint_worker.handler",
            code=lambda_.Code.from_asset(
                str(REPO_ROOT / "app" / "api"),
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir -r requirements.txt -t /asset-output "
                        "&& mkdir -p /asset-output/api "
                        "&& cp -r . /asset-output/api/",
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
                # Cognito not needed — worker is invoked by SQS, never
                # handles a user token directly.
                "ANTHROPIC_API_KEY_SECRET": anthropic_secret.secret_name,
            },
        )
        self.blueprint_worker_function.add_event_source(
            lambda_events.SqsEventSource(self.blueprint_queue, batch_size=1)
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

        cdk.CfnOutput(self, "ApiEndpoint", value=self.http_api.api_endpoint)
        cdk.CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        cdk.CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        cdk.CfnOutput(self, "ArtifactsBucketName", value=self.artifacts_bucket.bucket_name)
        cdk.CfnOutput(self, "RenderQueueUrl", value=self.render_queue.queue_url)
        cdk.CfnOutput(self, "WebBucketName", value=self.web_bucket.bucket_name)
        cdk.CfnOutput(
            self,
            "WebsiteUrl",
            value=f"http://{self.web_bucket.bucket_website_domain_name}",
        )
