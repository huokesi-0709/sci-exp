from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .schemas import InferenceQuery, RetrievedChunk


@dataclass(frozen=True)
class GenerationResult:
    text: str
    backend: str
    prompt_tokens: int | None = None
    generated_tokens: int | None = None


class Generator(Protocol):
    def generate(
        self,
        query: InferenceQuery,
        evidence: list[RetrievedChunk],
        *,
        configuration: str,
    ) -> GenerationResult: ...


def build_prompt(
    query: InferenceQuery,
    evidence: list[RetrievedChunk],
    *,
    configuration: str = "C2",
    context_character_limit: int | None = None,
) -> str:
    evidence_text = "\n".join(
        f"[{item.chunk.evidence_id}] {item.chunk.text}" for item in evidence
    )
    if context_character_limit is not None and context_character_limit >= 0:
        evidence_text = evidence_text[:context_character_limit]
    if not evidence_text:
        evidence_text = "无可用协议证据。"
    if configuration == "C0":
        instruction = (
            "你是离线应急助手。本配置不提供检索证据，只能给出保守的一般性安全"
            "提示；不得声称依据了本地协议，不得虚构辖区、电话或现场事实。"
        )
    else:
        instruction = (
            "你是离线应急助手。只能依据给定协议回答；证据不足时必须明确回退并"
            "请求补充信息。不得虚构。回答应短、可执行，并用方括号标注证据编号。"
        )
    return (
        f"{instruction}\n\n"
        f"问题：{query.text}\n"
        f"协议证据：\n{evidence_text}\n\n"
        "回答："
    )


class ExtractiveGenerator:
    """Deterministic smoke-test backend; it is not a research model."""

    backend_name = "extractive-smoke-only"

    def generate(
        self,
        query: InferenceQuery,
        evidence: list[RetrievedChunk],
        *,
        configuration: str,
    ) -> GenerationResult:
        if configuration == "C3":
            return GenerationResult(
                text=render_safety_fallback(query, "safe_fallback_configuration"),
                backend="deterministic-safety-template",
            )
        if configuration != "C0" and not evidence:
            return GenerationResult(
                text=render_safety_fallback(query, "no_applicable_protocol"),
                backend=self.backend_name,
            )
        if configuration == "C0":
            return GenerationResult(
                text="本配置未检索协议，仅可给出一般性安全提示；请以当地官方指令为准。",
                backend=self.backend_name,
            )
        statements = [
            f"{item.chunk.text} [{item.chunk.evidence_id}]" for item in evidence
        ]
        return GenerationResult(text="\n".join(statements), backend=self.backend_name)


class LlamaServerGenerator:
    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float = 120,
        max_tokens: int = 256,
        temperature: float = 0.0,
        api_style: str = "auto",
        model: str = "local",
        max_tokens_by_configuration: dict[str, int] | None = None,
        context_characters_by_configuration: dict[str, int] | None = None,
    ) -> None:
        if not endpoint:
            raise ValueError("llama_server backend requires generator.endpoint")
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.api_style = (
            "openai_chat"
            if api_style == "auto" and endpoint.rstrip("/").endswith("/v1/chat/completions")
            else "completion"
            if api_style == "auto"
            else api_style
        )
        if self.api_style not in {"completion", "openai_chat"}:
            raise ValueError("generator.api_style must be completion, openai_chat, or auto")
        self.model = model
        self.max_tokens_by_configuration = dict(max_tokens_by_configuration or {})
        self.context_characters_by_configuration = dict(
            context_characters_by_configuration or {}
        )

    def generate(
        self,
        query: InferenceQuery,
        evidence: list[RetrievedChunk],
        *,
        configuration: str,
    ) -> GenerationResult:
        if configuration == "C3":
            return GenerationResult(
                text=render_safety_fallback(query, "safe_fallback_configuration"),
                backend="deterministic-safety-template",
            )
        max_tokens = int(
            self.max_tokens_by_configuration.get(configuration, self.max_tokens)
        )
        prompt = build_prompt(
            query,
            evidence,
            configuration=configuration,
            context_character_limit=self.context_characters_by_configuration.get(
                configuration
            ),
        )
        if self.api_style == "openai_chat":
            request_value = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": self.temperature,
                "stop": ["</s>", "\n\n问题："],
            }
        else:
            request_value = {
                "prompt": prompt,
                "n_predict": max_tokens,
                "temperature": self.temperature,
                "stop": ["</s>", "\n\n问题："],
            }
        payload = json.dumps(request_value, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                value = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"llama-server request failed: {exc}") from exc
        usage = value.get("usage", {}) if isinstance(value.get("usage"), dict) else {}
        if self.api_style == "openai_chat":
            choices = value.get("choices", [])
            message = (
                choices[0].get("message", {})
                if isinstance(choices, list)
                and choices
                and isinstance(choices[0], dict)
                else {}
            )
            text = str(message.get("content", "")).strip()
        else:
            text = str(value.get("content", value.get("response", ""))).strip()
        if not text:
            raise RuntimeError("llama-server returned no generated text")
        timings = value.get("timings", {}) if isinstance(value.get("timings"), dict) else {}
        return GenerationResult(
            text=text,
            backend="llama-server",
            prompt_tokens=_optional_int(
                usage.get("prompt_tokens", timings.get("prompt_n"))
            ),
            generated_tokens=_optional_int(
                usage.get("completion_tokens", timings.get("predicted_n"))
            ),
        )


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def render_safety_fallback(query: InferenceQuery, reason: str) -> str:
    templates = {
        "out_of_scope": (
            "这个问题超出当前离线应急协议库的范围，无法安全作答。请联系相应的"
            "当地主管机构；如存在即时人身危险，请优先联系当地紧急服务。"
        ),
        "conflicting_evidence": (
            "检索到的协议存在可能冲突，当前不能给出确定性行动建议。请遵循现场"
            "最新官方指令，必要时转由人工应急人员判断。"
        ),
        "no_applicable_protocol": (
            "当前没有找到与地点、时间和场景均适用的协议证据。请补充所在地区、"
            "事件类型和现场危险，并以当地最新官方指令为准。"
        ),
        "resource_unavailable": (
            "设备资源不足，无法完成可靠检索或生成。请改用官方应急渠道或转人工"
            "处理；如存在即时危险，请优先撤离到安全位置。"
        ),
        "safe_fallback_configuration": (
            "当前信息不足或风险较高，无法安全给出确定性行动建议。请补充地点、"
            "受影响对象、现场危险和可用资源，并优先联系当地应急机构。"
        ),
    }
    return templates.get(reason, templates["safe_fallback_configuration"])


def make_generator(config: dict[str, object]) -> Generator:
    backend = str(config.get("backend", "extractive"))
    if backend == "extractive":
        return ExtractiveGenerator()
    if backend == "llama_server":
        return LlamaServerGenerator(
            str(config.get("endpoint", "")),
            timeout_seconds=float(config.get("timeout_seconds", 120)),
            max_tokens=int(config.get("max_tokens", 256)),
            temperature=float(config.get("temperature", 0.0)),
            api_style=str(config.get("api_style", "auto")),
            model=str(config.get("model", "local")),
            max_tokens_by_configuration={
                str(key): int(value)
                for key, value in dict(
                    config.get("max_tokens_by_configuration", {})
                ).items()
            },
            context_characters_by_configuration={
                str(key): int(value)
                for key, value in dict(
                    config.get("context_characters_by_configuration", {})
                ).items()
            },
        )
    raise ValueError(f"unsupported generator backend: {backend}")
