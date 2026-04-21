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

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(
                    name="isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
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
            description="Allow Lambda -> RDS",
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
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16_3),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.SMALL),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[rds_sg],
            multi_az=False,
            allocated_storage=20,
            max_allocated_storage=50,
            storage_encryption_key=self.key,
            credentials=rds.Credentials.from_secret(self.db_secret),
            backup_retention=cdk.Duration.days(7 if stage_name == "prod" else 1),
            deletion_protection=stage_name == "prod",
            removal_policy=cdk.RemovalPolicy.SNAPSHOT if stage_name == "prod" else cdk.RemovalPolicy.DESTROY,
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

        self.api_function = lambda_.Function(
            self,
            "ApiFunction",
            function_name=f"slideforge-{stage_name}-api",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="main.handler",
            code=lambda_.Code.from_asset(
                str(REPO_ROOT / "app" / "api"),
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir -r requirements.txt -t /asset-output "
                        "&& cp -r . /asset-output/",
                    ],
                ),
            ),
            memory_size=1024,
            timeout=cdk.Duration.seconds(60),
            role=api_role,
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[lambda_sg],
            environment={
                "ENV": stage_name,
                "S3_BUCKET": self.artifacts_bucket.bucket_name,
                "DB_SECRET_ARN": self.db_secret.secret_arn,
                "DB_ENDPOINT": self.db.instance_endpoint.hostname,
                "RENDER_QUEUE_URL": self.render_queue.queue_url,
                "COGNITO_USER_POOL_ID": self.user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": self.user_pool_client.user_pool_client_id,
                "ANTHROPIC_API_KEY_SECRET": anthropic_secret.secret_name,
            },
        )

        self.http_api = apigw2.HttpApi(
            self,
            "HttpApi",
            api_name=f"slideforge-{stage_name}",
            cors_preflight=apigw2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigw2.CorsHttpMethod.ANY],
                allow_headers=["Authorization", "Content-Type"],
            ),
        )
        self.http_api.add_routes(
            path="/{proxy+}",
            methods=[apigw2.HttpMethod.ANY],
            integration=apigw2_integ.HttpLambdaIntegration(
                "ApiIntegration",
                handler=self.api_function,
            ),
        )

        cdk.CfnOutput(self, "ApiEndpoint", value=self.http_api.api_endpoint)
        cdk.CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        cdk.CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        cdk.CfnOutput(self, "ArtifactsBucketName", value=self.artifacts_bucket.bucket_name)
        cdk.CfnOutput(self, "RenderQueueUrl", value=self.render_queue.queue_url)
