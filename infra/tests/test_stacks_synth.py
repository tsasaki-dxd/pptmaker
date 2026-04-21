"""Smoke test: CDK app synthesizes without errors."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

INFRA = Path(__file__).resolve().parent.parent


def test_cdk_synth_runs() -> None:
    env = os.environ.copy()
    env.setdefault("CDK_DEFAULT_ACCOUNT", "000000000000")
    env.setdefault("CDK_DEFAULT_REGION", "ap-northeast-1")
    result = subprocess.run(
        ["npx", "cdk", "synth", "--quiet"],
        cwd=INFRA,
        env=env,
        capture_output=True,
        text=True,
    )
    # If cdk is not installed in CI, skip. Otherwise fail fast.
    if result.returncode != 0 and "npx: command not found" not in result.stderr:
        raise AssertionError(result.stderr[-2000:])
