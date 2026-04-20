#!/usr/bin/env python3
"""
SlideForge CDK entrypoint.

Phase 1: single AWS account, stack prefix separates Dev / Stg / Prod.
Phase 2 (planned): multi-account via `env={...}` + CrossAccount keys.
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

# Pipeline (deploys the two app stages below via self-mutation)
PipelineStack(
    app,
    "SlideForgePipelineStack",
    env=env,
    github_owner=os.environ.get("GITHUB_OWNER", "tsasaki-dxd"),
    github_repo=os.environ.get("GITHUB_REPO", "pptmaker"),
    ecr_repo_name=os.environ.get("ECR_REPOSITORY", "slideforge/render"),
)

# Direct-deployable stages (useful for local cdk deploy without pipeline)
AppStage(app, "SlideForge-Dev", env=env, stage_name="dev")
AppStage(app, "SlideForge-Stg", env=env, stage_name="stg")
AppStage(app, "SlideForge-Prod", env=env, stage_name="prod")

app.synth()
