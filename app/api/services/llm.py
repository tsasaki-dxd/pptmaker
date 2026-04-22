"""
Claude API client for blueprint generation, revision, and brush.

Uses Prompt Caching (ephemeral) on the immutable system prompt sections.
See docs/01_prompt_engineering.md §8.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from ..config import get_settings

log = logging.getLogger("slideforge.llm")

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _load(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


@dataclass
class LLMResult:
    text: str
    usage: dict[str, int]
    model: str


_cached_api_key: str | None = None


def _get_api_key() -> str:
    """Resolve the Anthropic API key.

    - ANTHROPIC_API_KEY env var wins if present (local dev, CI).
    - Otherwise fetch the secret named by ANTHROPIC_API_KEY_SECRET from
      Secrets Manager. Lambda role must grant secretsmanager:GetSecretValue.
    Cached at module scope for the lifetime of the Lambda container.
    """
    global _cached_api_key
    if _cached_api_key is not None:
        return _cached_api_key

    direct = os.environ.get("ANTHROPIC_API_KEY", "")
    if direct:
        _cached_api_key = direct
        return direct

    settings = get_settings()
    secret_name = settings.anthropic_api_key_secret
    if not secret_name:
        _cached_api_key = ""
        return ""

    import boto3

    sm = boto3.client("secretsmanager", region_name=settings.aws_region)
    val = sm.get_secret_value(SecretId=secret_name)
    _cached_api_key = val["SecretString"]
    return _cached_api_key


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = Anthropic(api_key=_get_api_key())

    def blueprint(
        self,
        user_intent: str,
        required_sections: list[str],
        aux_context: str | None,
        template_summary: str,
        figure_catalog: str,
    ) -> LLMResult:
        system_blocks = [
            {
                "type": "text",
                "text": _load("blueprint_system.txt"),
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": f"【テンプレートプロファイル】\n{template_summary}\n\n【figure_type カタログ】\n{figure_catalog}",
                "cache_control": {"type": "ephemeral"},
            },
        ]
        user_prompt = _load("blueprint_user.txt").format(
            USER_INTENT=user_intent,
            REQUIRED_SECTIONS=", ".join(required_sections) or "(指定なし)",
            AUX_CONTEXT=aux_context or "(なし)",
        )
        return self._call(
            model=self.settings.claude_model_blueprint,
            system=system_blocks,
            user=user_prompt,
            max_tokens=4096,
            temperature=0.4,
        )

    def revision_patch(self, current_blueprint: dict[str, Any], instruction: str) -> LLMResult:
        system = [
            {
                "type": "text",
                "text": _load("revision_system.txt"),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        user_prompt = (
            f"【現 Blueprint】\n```json\n{json.dumps(current_blueprint, ensure_ascii=False)}\n```\n"
            f"【修正指示】\n{instruction}\n"
            "RFC 6902 JSON Patch 配列のみを返してください。"
        )
        return self._call(
            model=self.settings.claude_model_revision,
            system=system,
            user=user_prompt,
            max_tokens=2048,
            temperature=0.2,
        )

    def brush(self, blueprint: dict[str, Any]) -> LLMResult:
        system = [{"type": "text", "text": _load("brush_system.txt")}]
        user_prompt = (
            "以下 Blueprint の本文テキストを自然な日本語に整えて、"
            "JSON 構造はそのまま返してください。\n"
            f"```json\n{json.dumps(blueprint, ensure_ascii=False)}\n```"
        )
        return self._call(
            model=self.settings.claude_model_brush,
            system=system,
            user=user_prompt,
            max_tokens=3000,
            temperature=0.3,
        )

    def _call(
        self,
        *,
        model: str,
        system: list[dict[str, Any]],
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResult:
        resp = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0),
        }
        log.info("llm_call model=%s usage=%s", model, usage)
        return LLMResult(text=text, usage=usage, model=model)


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from an LLM response.

    Accepts bare JSON or JSON inside a ```json ... ``` fence.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.rsplit("```", 1)[0]
    return json.loads(stripped.strip())
