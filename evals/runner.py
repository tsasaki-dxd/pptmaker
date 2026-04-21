"""
LLM Eval runner.

Loads cases from evals/cases/*.yaml, calls the Blueprint Builder, validates
output shape, scores with LLM-as-a-Judge, and writes a JSON report.

Usage:
  python -m evals.runner               # run all cases
  python -m evals.runner --case case01 # single case
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from api.services.blueprint_builder import BlueprintBuildError, build_blueprint  # noqa: E402
from api.services.llm import LLMClient, extract_json  # noqa: E402

log = logging.getLogger("slideforge.eval")
logging.basicConfig(level=logging.INFO)

CASES_DIR = Path(__file__).resolve().parent / "cases"
REPORT_PATH = Path(__file__).resolve().parent / "report.json"

JUDGE_PROMPT = """あなたは提案書品質評価者です。
以下の Blueprint を 3 観点で 1〜5 点で評価し、次の JSON のみ返してください。
{"scores": {"n": int(自然さ), "s": int(構成妥当性), "f": int(図表選択)}, "reasons": "短文"}

Blueprint:
"""


@dataclass
class CaseResult:
    name: str
    ok: bool
    scores: dict[str, int] | None
    reasons: str | None
    error: str | None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default=None)
    args = parser.parse_args()

    files = sorted(CASES_DIR.glob("*.yaml"))
    if args.case:
        files = [f for f in files if f.stem == args.case]
    if not files:
        log.error("no cases found")
        return 2

    llm = LLMClient()
    results: list[CaseResult] = []

    for f in files:
        spec = yaml.safe_load(f.read_text(encoding="utf-8"))
        log.info("case %s", f.stem)
        results.append(_run_case(llm, f.stem, spec))

    REPORT_PATH.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    failed = [r for r in results if not r.ok]
    if failed:
        log.error("%d / %d failed", len(failed), len(results))
        return 1
    log.info("all %d cases passed", len(results))
    return 0


def _run_case(llm: LLMClient, name: str, spec: dict[str, Any]) -> CaseResult:
    try:
        bp = build_blueprint(
            llm=llm,
            user_intent=spec["intent"],
            required_sections=spec.get("required_sections", []),
            aux_context=spec.get("aux_context"),
            template_summary=spec.get("template_summary", "(テンプレート不明)"),
            figure_catalog=spec.get("figure_catalog", ""),
        )
    except BlueprintBuildError as e:
        return CaseResult(name=name, ok=False, scores=None, reasons=None, error=str(e))

    scores, reasons = _judge(llm, bp)
    pass_floor = spec.get("pass_floor", {"n": 3, "s": 3, "f": 3})
    ok = all(scores.get(k, 0) >= v for k, v in pass_floor.items())
    return CaseResult(name=name, ok=ok, scores=scores, reasons=reasons, error=None)


def _judge(llm: LLMClient, bp: dict[str, Any]) -> tuple[dict[str, int], str]:
    result = llm._call(  # type: ignore[attr-defined]
        model=llm.settings.claude_model_blueprint,
        system=[{"type": "text", "text": "あなたは評価者です。JSON のみ返答してください。"}],
        user=JUDGE_PROMPT + json.dumps(bp, ensure_ascii=False),
        max_tokens=400,
        temperature=0.0,
    )
    obj = extract_json(result.text)
    return obj.get("scores", {}), obj.get("reasons", "")


if __name__ == "__main__":
    raise SystemExit(main())
