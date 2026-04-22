"""
CodePipeline Stack (simplified single-stage CD).

Scope: take a pre-synthesized cloud assembly + `app/web` source uploaded
to S3 by GHA, and in one CodeBuild action do everything a deploy needs:

  1. cdk deploy App-prod                   (applies CFN template)
  2. read App-prod's CfnOutputs            (ApiEndpoint, WebBucketName, ...)
  3. npm run build in app/web              (static Next.js export)
  4. write runtime config.json             (api endpoint + cognito ids)
  5. aws s3 sync out/ -> web bucket        (publish the SPA)

GHA's job ends at "StartPipelineExecution" — no waiting, no reading
CfnOutputs, no S3 sync. The pipeline owns the deploy end-to-end.

Deliberately NOT using `pipelines.CodePipeline` — self-mutation,
Assets stage, CodeStar Connection, and the Synth stage it insisted
on were the source of every pipeline-side bug we hit. Here we own
the orchestration explicitly.
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

        # GHA uploads `deploy.zip` here, then calls StartPipelineExecution.
        # The zip is expected to contain:
        #   cdk.out/    pre-synthesized cloud assembly
        #   app/web/    Next.js source (pipeline runs `npm run build`)
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

        source_output = codepipeline.Artifact("DeployInput")

        deploy_project = codebuild.PipelineProject(
            self,
            "CdkDeployProject",
            project_name="SlideForge-Deploy",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5,
                privileged=True,
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
                                "set -euo pipefail",
                                "ls -la",
                                "test -d cdk.out || (echo 'cdk.out/ missing in artifact' && exit 1)",
                                "test -d app/web || (echo 'app/web/ missing in artifact' && exit 1)",
                                # 0. Recover from a previous deploy that left the stack in
                                # an un-updatable state. Without this, the very next cdk
                                # deploy asks for interactive confirmation that CodeBuild
                                # can't provide and fails with TtyNotAttached.
                                'echo "=== pre-flight: check App-prod state ==="',
                                'STATUS=$(aws cloudformation describe-stacks --stack-name App-prod --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "DOES_NOT_EXIST")',
                                'echo "App-prod status: $STATUS"',
                                'case "$STATUS" in'
                                ' CREATE_FAILED|ROLLBACK_COMPLETE|ROLLBACK_FAILED|DELETE_FAILED|REVIEW_IN_PROGRESS|UPDATE_ROLLBACK_FAILED)'
                                '   echo "Deleting stuck stack before redeploy...";'
                                '   aws cloudformation delete-stack --stack-name App-prod;'
                                '   aws cloudformation wait stack-delete-complete --stack-name App-prod;'
                                '   echo "Delete complete.";;'
                                ' esac',
                                # 1. Apply CFN (idempotent; rolls back on failure so next
                                #    run can update without stuck-state intervention)
                                'echo "=== cdk deploy App-prod ==="',
                                "cdk deploy App-prod --app cdk.out --require-approval never --outputs-file /tmp/deploy-outputs.json",
                                "cat /tmp/deploy-outputs.json",
                                # 2. Pull outputs we need for the web deploy
                                'echo "=== reading CfnOutputs ==="',
                                'OUT=$(aws cloudformation describe-stacks --stack-name App-prod --query "Stacks[0].Outputs" --output json)',
                                'get() { echo "$OUT" | jq -r --arg k "$1" \'.[] | select(.OutputKey==$k) | .OutputValue\'; }',
                                'API_ENDPOINT=$(get ApiEndpoint)',
                                'USER_POOL_ID=$(get UserPoolId)',
                                'USER_POOL_CLIENT_ID=$(get UserPoolClientId)',
                                'WEB_BUCKET=$(get WebBucketName)',
                                'WEBSITE_URL=$(get WebsiteUrl)',
                                'echo "Website will be at: $WEBSITE_URL"',
                                # 3. Build the SPA
                                'echo "=== build Next.js ==="',
                                "cd app/web",
                                "if [ -f package-lock.json ]; then npm ci; else npm install --no-audit --no-fund; fi",
                                "npm run build",
                                # 4. Inject runtime config
                                'cat > out/config.json <<EOF\n'
                                '{\n'
                                '  "apiEndpoint": "$API_ENDPOINT",\n'
                                '  "userPoolId": "$USER_POOL_ID",\n'
                                '  "userPoolClientId": "$USER_POOL_CLIENT_ID",\n'
                                '  "region": "$AWS_DEFAULT_REGION"\n'
                                '}\n'
                                'EOF',
                                "cat out/config.json",
                                # 5. Sync to web bucket
                                'echo "=== sync to S3 web bucket ==="',
                                'aws s3 sync out/ "s3://$WEB_BUCKET/" --delete --cache-control "public, max-age=300"',
                                'aws s3 cp out/config.json "s3://$WEB_BUCKET/config.json" --cache-control "no-store"',
                                'echo "=== done. Website: $WEBSITE_URL ==="',
                            ],
                        },
                    },
                }
            ),
        )

        # CodeBuild role needs to: assume CDK bootstrap roles, call CFN,
        # read/write many services. AdministratorAccess is the pragmatic
        # Phase 1 choice; Phase 2 tightens to least-privilege.
        deploy_project.role.add_managed_policy(  # type: ignore[union-attr]
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess"),
        )

        pipeline = codepipeline.Pipeline(
            self,
            "Pipeline",
            # No fixed pipeline_name — avoids collision with any pipeline
            # previously deployed under the same name during CFN updates.
            artifact_bucket=self.deploy_bucket,
            restart_execution_on_update=False,
            stages=[
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[
                        cpa.S3SourceAction(
                            action_name="S3Source",
                            bucket=self.deploy_bucket,
                            bucket_key="latest/deploy.zip",
                            trigger=cpa.S3Trigger.NONE,
                            output=source_output,
                        ),
                    ],
                ),
                codepipeline.StageProps(
                    stage_name="Deploy",
                    actions=[
                        cpa.CodeBuildAction(
                            action_name="CdkDeployAndWebSync",
                            project=deploy_project,
                            input=source_output,
                        ),
                    ],
                ),
            ],
        )

        cdk.CfnOutput(self, "PipelineName", value=pipeline.pipeline_name)
        cdk.CfnOutput(self, "DeployBucketName", value=self.deploy_bucket.bucket_name)
