"""
CodePipeline Stack (simplified single-stage CD).

Scope: take a pre-synthesized cloud assembly uploaded to S3 by GHA,
run `cdk deploy` inside a CodeBuild action, apply the resulting
template to `SlideForge-App-prod`. Nothing more.

Deliberately NOT using `pipelines.CodePipeline` — self-mutation,
Assets stage, CodeStar Connection, and the Synth stage it insisted
on were the source of every pipeline-side bug we hit. Here we own
the orchestration explicitly: GHA synths, uploads artifacts, and
calls StartPipelineExecution. Pipeline only does CFN deploy.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as cpa
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


class PipelineStack(cdk.Stack):
    def __init__(self, scope: Construct, id_: str, **kwargs) -> None:
        super().__init__(scope, id_, **kwargs)

        # GHA uploads `cdk.out.zip` here, then calls StartPipelineExecution.
        self.deploy_bucket = s3.Bucket(
            self,
            "DeployArtifacts",
            bucket_name=f"slideforge-deploy-{self.account}",
            versioned=True,  # CodePipeline S3 source requires versioned buckets.
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="expire-old-artifacts",
                    noncurrent_version_expiration=cdk.Duration.days(30),
                )
            ],
        )

        source_output = codepipeline.Artifact("CdkOutput")

        # CodeBuild project that runs `cdk deploy` against the pre-synthesized
        # cloud assembly in the source artifact.
        deploy_project = codebuild.PipelineProject(
            self,
            "CdkDeployProject",
            project_name="SlideForge-CdkDeploy",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5,
                privileged=True,  # not used today, kept for future Docker assets
            ),
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "runtime-versions": {"nodejs": "20", "python": "3.12"},
                            "commands": [
                                "npm install -g aws-cdk",
                            ],
                        },
                        "build": {
                            "commands": [
                                # The zip from S3 is extracted at $CODEBUILD_SRC_DIR.
                                # Expect it to contain a `cdk.out/` directory.
                                "ls -la",
                                "test -d cdk.out || (echo 'cdk.out not found in artifact' && exit 1)",
                                # `cdk deploy -a cdk.out` skips synth and uses the
                                # cloud assembly as-is. Asset publishing happens here
                                # (or is a no-op if GHA already published them).
                                "cdk deploy App-prod "
                                "--app cdk.out "
                                "--require-approval never "
                                "--no-rollback "
                                "--outputs-file deploy-outputs.json",
                                "cat deploy-outputs.json || true",
                            ],
                        },
                    },
                    "artifacts": {
                        "files": ["deploy-outputs.json"],
                    },
                }
            ),
        )

        # The CodeBuild role needs to assume the CDK bootstrap deploy/publishing
        # roles (created by `cdk bootstrap`). AdministratorAccess is the
        # pragmatic Phase 1 choice; Phase 2 tightens to the four named cdk-*
        # roles explicitly.
        deploy_project.role.add_managed_policy(  # type: ignore[union-attr]
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess"),
        )

        codepipeline.Pipeline(
            self,
            "Pipeline",
            pipeline_name="SlideForgePipeline",
            artifact_bucket=self.deploy_bucket,
            restart_execution_on_update=False,
            stages=[
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[
                        cpa.S3SourceAction(
                            action_name="S3Source",
                            bucket=self.deploy_bucket,
                            bucket_key="latest/cdk.out.zip",
                            # Triggered explicitly by GHA via StartPipelineExecution;
                            # do not also subscribe to EventBridge.
                            trigger=cpa.S3Trigger.NONE,
                            output=source_output,
                        ),
                    ],
                ),
                codepipeline.StageProps(
                    stage_name="Deploy",
                    actions=[
                        cpa.CodeBuildAction(
                            action_name="CdkDeploy",
                            project=deploy_project,
                            input=source_output,
                        ),
                    ],
                ),
            ],
        )

        cdk.CfnOutput(self, "PipelineName", value="SlideForgePipeline")
        cdk.CfnOutput(self, "DeployBucketName", value=self.deploy_bucket.bucket_name)
