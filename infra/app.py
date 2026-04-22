#!/usr/bin/env python3
"""
SlideForge CDK entrypoint.

Two top-level stacks:
  * SlideForgePipelineStack   CodePipeline + S3 artifact bucket (CD side)
  * App-prod                  the actual application (data plane + app plane)

GHA calls `cdk synth` to produce both templates. It then:
  1. uploads the cloud assembly to the SlideForgePipelineStack's
     DeployArtifacts S3 bucket
  2. calls StartPipelineExecution, which makes the pipeline apply the
     freshly synthesized App-prod template via CloudFormation.

No CDK Pipelines self-mutation, no CodeStar Connection, no Stage.
"""

from __future__ import annotations

import os

import aws_cdk as cdk
from stacks.app_stack import AppStack
from stacks.pipeline_stack import PipelineStack

app = cdk.App()

account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "ap-northeast-1")

# Pre-populate the AZ context cache so that `Stack.availability_zones`
# does not issue a `DescribeAvailabilityZones` call during synth. In CI
# we synth against a placeholder account (000000000000) with no
# credentials, which would otherwise fail with "Need to perform AWS
# calls for account ..., but no credentials have been configured".
if account:
    app.node.set_context(
        f"availability-zones:account={account}:region={region}",
        [f"{region}a", f"{region}c"],
    )

env = cdk.Environment(account=account, region=region)

PipelineStack(app, "SlideForgePipelineStack", env=env)

AppStack(app, "App-prod", env=env, stage_name="prod")

app.synth()
