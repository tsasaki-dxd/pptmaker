"""Data plane: VPC, RDS, S3, Secrets Manager, KMS."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_kms as kms
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct


class DataStack(cdk.Stack):
    def __init__(self, scope: Construct, id_: str, *, stage_name: str, **kwargs) -> None:
        super().__init__(scope, id_, **kwargs)

        self.stage_name = stage_name

        # Customer-managed KMS key for S3/RDS/Secrets
        self.key = kms.Key(
            self,
            "DataKey",
            alias=f"alias/slideforge-{stage_name}-data",
            enable_key_rotation=True,
            removal_policy=cdk.RemovalPolicy.RETAIN if stage_name == "prod" else cdk.RemovalPolicy.DESTROY,
        )

        # Artifacts bucket (templates, projects, previews, outputs)
        self.artifacts_bucket = s3.Bucket(
            self,
            "ArtifactsBucket",
            bucket_name=None,  # let CDK generate a unique name
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

        # VPC (minimal, only to host RDS privately)
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

        self.rds_security_group = ec2.SecurityGroup(
            self,
            "RdsSg",
            vpc=self.vpc,
            description="RDS SG (allow from Lambda SG only)",
            allow_all_outbound=False,
        )

        # RDS db.t4g.small single-AZ (Phase 1 minimal)
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
            security_groups=[self.rds_security_group],
            multi_az=False,
            allocated_storage=20,
            max_allocated_storage=50,
            storage_encryption_key=self.key,
            credentials=rds.Credentials.from_secret(self.db_secret),
            backup_retention=cdk.Duration.days(7 if stage_name == "prod" else 1),
            deletion_protection=stage_name == "prod",
            removal_policy=cdk.RemovalPolicy.SNAPSHOT if stage_name == "prod" else cdk.RemovalPolicy.DESTROY,
        )

        self.db_endpoint = self.db.instance_endpoint.hostname

        # Anthropic API key placeholder (populated manually after bootstrap)
        self.anthropic_secret = sm.Secret(
            self,
            "AnthropicApiKey",
            secret_name=f"slideforge/{stage_name}/anthropic",
            description="Anthropic Claude API key (set value manually after stack creation)",
            encryption_key=self.key,
        )
