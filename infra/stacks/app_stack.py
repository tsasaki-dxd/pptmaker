"""Application plane: API Lambda, SQS, Render Lambda Container, Cognito."""

from __future__ import annotations

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_apigatewayv2 as apigw2
from aws_cdk import aws_apigatewayv2_integrations as apigw2_integ
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_events
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
        artifacts_bucket: s3.IBucket,
        db_secret: sm.ISecret,
        db_endpoint: str,
        db_vpc: ec2.IVpc,
        db_security_group: ec2.ISecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, id_, **kwargs)

        # Cognito
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

        # Render queue
        self.render_dlq = sqs.Queue(
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
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=self.render_dlq),
        )

        # Lambda Security Group (allowed to reach RDS)
        self.lambda_sg = ec2.SecurityGroup(
            self,
            "LambdaSg",
            vpc=db_vpc,
            description="SlideForge Lambda SG",
            allow_all_outbound=True,
        )
        db_security_group.add_ingress_rule(
            peer=self.lambda_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow Lambda -> RDS",
        )

        # Render Lambda (container image from local Dockerfile at app/render/)
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
                "S3_BUCKET": artifacts_bucket.bucket_name,
            },
        )
        artifacts_bucket.grant_read_write(self.render_function)
        self.render_function.add_event_source(
            lambda_events.SqsEventSource(self.render_queue, batch_size=1)
        )

        # Anthropic secret reference (created in DataStack by naming convention)
        anthropic_secret = sm.Secret.from_secret_name_v2(
            self,
            "AnthropicKeyRef",
            f"slideforge/{stage_name}/anthropic",
        )

        # API Lambda (zip deployment from app/api)
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
        artifacts_bucket.grant_read_write(api_role)
        db_secret.grant_read(api_role)
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
            vpc=db_vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[self.lambda_sg],
            environment={
                "ENV": stage_name,
                "AWS_REGION_OVERRIDE": self.region,
                "S3_BUCKET": artifacts_bucket.bucket_name,
                "DB_SECRET_ARN": db_secret.secret_arn,
                "DB_ENDPOINT": db_endpoint,
                "RENDER_QUEUE_URL": self.render_queue.queue_url,
                "COGNITO_USER_POOL_ID": self.user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": self.user_pool_client.user_pool_client_id,
                "ANTHROPIC_API_KEY_SECRET": anthropic_secret.secret_name,
            },
        )

        # HTTP API
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
        cdk.CfnOutput(self, "ArtifactsBucket", value=artifacts_bucket.bucket_name)
        cdk.CfnOutput(self, "RenderQueueUrl", value=self.render_queue.queue_url)
