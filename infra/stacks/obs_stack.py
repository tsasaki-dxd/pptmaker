"""Observability: CloudWatch Alarms, Dashboards."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class ObservabilityStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id_: str,
        *,
        stage_name: str,
        api_function: lambda_.IFunction,
        render_function: lambda_.IFunction,
        **kwargs,
    ) -> None:
        super().__init__(scope, id_, **kwargs)

        api_errors = cw.Alarm(
            self,
            "ApiErrors",
            metric=api_function.metric_errors(period=cdk.Duration.minutes(5)),
            threshold=5,
            evaluation_periods=3,
            alarm_description=f"API Lambda errors ({stage_name})",
        )

        render_failures = cw.Alarm(
            self,
            "RenderFailures",
            metric=render_function.metric_errors(period=cdk.Duration.minutes(5)),
            threshold=3,
            evaluation_periods=3,
            alarm_description=f"Render Lambda errors ({stage_name})",
        )

        api_duration = cw.Alarm(
            self,
            "ApiDuration",
            metric=api_function.metric_duration(period=cdk.Duration.minutes(5)),
            threshold=5000,  # ms
            evaluation_periods=3,
            alarm_description=f"API p95 duration > 5s ({stage_name})",
        )

        dashboard = cw.Dashboard(
            self,
            "SlideForgeDashboard",
            dashboard_name=f"SlideForge-{stage_name}",
        )
        dashboard.add_widgets(
            cw.GraphWidget(
                title="API Invocations / Errors",
                left=[api_function.metric_invocations(), api_function.metric_errors()],
                width=12,
            ),
            cw.GraphWidget(
                title="Render Invocations / Errors",
                left=[render_function.metric_invocations(), render_function.metric_errors()],
                width=12,
            ),
            cw.GraphWidget(
                title="API Duration (ms)",
                left=[api_function.metric_duration()],
                width=12,
            ),
        )

        self.alarms = [api_errors, render_failures, api_duration]
