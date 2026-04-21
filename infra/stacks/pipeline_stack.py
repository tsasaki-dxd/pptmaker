"""
CodePipeline Stack.

Source: ECR image with tag `prod` pushed by GitHub Actions. The pipeline
self-mutates and deploys to the single Prod stack in this account.
Phase 1 runs a single stage only (main merge == production deploy).
"""

from __future__ import annotations

import os

import aws_cdk as cdk
from aws_cdk import aws_ecr as ecr
from aws_cdk import pipelines
from constructs import Construct

from stages.app_stage import AppStage


class PipelineStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id_: str,
        *,
        github_owner: str,
        github_repo: str,
        ecr_repo_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id_, **kwargs)

        # The source is the GitHub repo itself for infra; app image is pulled
        # separately at deploy time. For the infra pipeline we use CodeStar
        # Connections (pre-created manually during bootstrap).
        connection_arn = os.environ.get("CODESTAR_CONNECTION_ARN", "")
        if not connection_arn:
            # Allow synth without the connection so that `cdk synth` works in CI.
            connection_arn = "arn:aws:codeconnections:ap-northeast-1:000000000000:connection/placeholder"

        source = pipelines.CodePipelineSource.connection(
            f"{github_owner}/{github_repo}",
            "main",
            connection_arn=connection_arn,
        )

        synth = pipelines.ShellStep(
            "Synth",
            input=source,
            commands=[
                "cd infra",
                "pip install -r requirements.txt",
                "npm install -g aws-cdk",
                "cdk synth",
            ],
            primary_output_directory="infra/cdk.out",
        )

        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            pipeline_name="SlideForgePipeline",
            synth=synth,
            cross_account_keys=False,  # Phase 1: single account
            docker_enabled_for_synth=True,
        )

        pipeline.add_stage(
            AppStage(self, "Prod", env=cdk.Environment(account=self.account, region=self.region), stage_name="prod"),
        )

        # The ECR repo is created by bootstrap.yml (outside CDK) because GHA
        # needs to push images to it before this stack exists. Reference the
        # existing repo rather than re-declaring it to avoid the
        # "resource already exists" change-set validation error.
        ecr.Repository.from_repository_name(self, "RenderEcrRepo", ecr_repo_name)

        cdk.CfnOutput(
            self,
            "PipelineName",
            value="SlideForgePipeline",
            description="Console: CodePipeline",
        )
