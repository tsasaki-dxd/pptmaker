#!/usr/bin/env python3
"""
SlideForge CDK entrypoint.

Phase 1: single AWS account, single stage (Prod only). main merge == prod deploy.
Phase 2 (planned): reintroduce Stg (and Dev) as separate AWS accounts.
"""

from __future__ import annotations

import os

import aws_cdk as cdk

from stacks.pipeline_stack import PipelineStack
from stages.app_stage import AppStage

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "ap-northeast-1"),
)

# Pipeline (deploys the Prod stage below via self-mutation)
PipelineStack(
    app,
    "SlideForgePipelineStack",
    env=env,
    github_owner=os.environ.get("GITHUB_OWNER", "tsasaki-dxd"),
    github_repo=os.environ.get("GITHUB_REPO", "pptmaker"),
    ecr_repo_name=os.environ.get("ECR_REPOSITORY", "slideforge/render"),
)

# Direct-deployable stage (useful for local cdk deploy without pipeline)
AppStage(app, "SlideForge-Prod", env=env, stage_name="prod")

app.synth()
