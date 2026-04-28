#!/usr/bin/env python3
"""
SlideForge CDK entrypoint.

Stacks:
  * SlideForgePipelineStack   CodePipeline + S3 artifact bucket (CD side)
  * App-prod                  the actual application (data plane + app plane)
  * Cert-prod                 (optional) ACM cert in us-east-1 — only
                              created when `custom_domain` context is set,
                              and consumed by App-prod via CDK
                              cross-region references.

GHA calls `cdk synth` to produce both templates. It then:
  1. uploads the cloud assembly to the SlideForgePipelineStack's
     DeployArtifacts S3 bucket
  2. calls StartPipelineExecution, which makes the pipeline apply the
     freshly synthesized App-prod template via CloudFormation.

No CDK Pipelines self-mutation, no CodeStar Connection, no Stage.

Custom-domain rollout:
  * Phase A (cert provisioning): set `custom_domain` to the desired
    hostname (e.g. "slideforge.dx-design.co.jp"). Deploy. CertStack
    enters CREATE_IN_PROGRESS while ACM waits for the validation
    CNAME — operator adds it to スターサーバー manually.
  * Phase B (CloudFront cutover): once the cert is validated, the
    same `custom_domain` value is enough to make AppStack swap the
    public S3 website for a private S3 + CloudFront distribution.
"""

from __future__ import annotations

import os

import aws_cdk as cdk
from stacks.app_stack import AppStack
from stacks.cert_stack import CertStack
from stacks.pipeline_stack import PipelineStack

app = cdk.App()

account = os.environ.get("CDK_DEFAULT_ACCOUNT")

# Each stack pins its own region. Don't read CDK_DEFAULT_REGION here:
# `cdk bootstrap aws://<acct>/us-east-1` sets CDK_DEFAULT_REGION to
# us-east-1, and if AppStack picked that up it would try to synth its
# VPC (whose AZs are hardcoded `ap-northeast-1a/c`) for us-east-1 and
# fail with "Given VPC availabilityZones must be a subset of the
# stack's availability zones".
APP_REGION = "ap-northeast-1"
CERT_REGION = "us-east-1"  # CloudFront cert requirement

# Pre-populate the AZ context cache so that `Stack.availability_zones`
# does not issue a `DescribeAvailabilityZones` call during synth. In CI
# we synth against a placeholder account (000000000000) with no
# credentials, which would otherwise fail with "Need to perform AWS
# calls for account ..., but no credentials have been configured".
if account:
    for region in (APP_REGION, CERT_REGION):
        app.node.set_context(
            f"availability-zones:account={account}:region={region}",
            [f"{region}a", f"{region}c"],
        )

app_env = cdk.Environment(account=account, region=APP_REGION)

# Custom-domain feature flag. Empty / unset = current behavior
# (public S3 website, no CloudFront). Set in cdk.json -> context, or
# pass per-deploy via `--context custom_domain=slideforge.dx-design.co.jp`.
custom_domain = (app.node.try_get_context("custom_domain") or "").strip() or None

cert_stack: CertStack | None = None
if custom_domain:
    cert_stack = CertStack(
        app,
        "Cert-prod",
        domain_name=custom_domain,
        # CloudFront requires the cert to live in us-east-1 regardless
        # of where the distribution is consumed.
        env=cdk.Environment(account=account, region=CERT_REGION),
        cross_region_references=True,
    )

PipelineStack(app, "SlideForgePipelineStack", env=app_env)

AppStack(
    app,
    "App-prod",
    env=app_env,
    stage_name="prod",
    custom_domain=custom_domain,
    custom_domain_certificate=cert_stack.certificate if cert_stack else None,
    cross_region_references=True,
)

app.synth()
