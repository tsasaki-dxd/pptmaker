"""App-level Stage: data + app + observability."""

from __future__ import annotations

import aws_cdk as cdk
from constructs import Construct

from stacks.app_stack import AppStack
from stacks.data_stack import DataStack
from stacks.obs_stack import ObservabilityStack


class AppStage(cdk.Stage):
    def __init__(
        self,
        scope: Construct,
        id_: str,
        *,
        env: cdk.Environment,
        stage_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id_, env=env, **kwargs)

        data = DataStack(self, f"Data-{stage_name}", stage_name=stage_name)
        app = AppStack(
            self,
            f"App-{stage_name}",
            stage_name=stage_name,
            artifacts_bucket=data.artifacts_bucket,
            db_secret=data.db_secret,
            db_endpoint=data.db_endpoint,
            db_vpc=data.vpc,
            db_security_group=data.rds_security_group,
        )
        ObservabilityStack(
            self,
            f"Obs-{stage_name}",
            stage_name=stage_name,
            api_function=app.api_function,
            render_function=app.render_function,
        )
