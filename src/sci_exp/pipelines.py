from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .generation import GenerationResult, Generator, render_safety_fallback
from .retrieval import (
    BM25Index,
    HybridIndex,
    build_second_step_query,
    detect_evidence_conflicts,
    filter_applicable_protocols,
    merge_ranked_results,
    protocol_aware_rerank,
)
from .schemas import QueryRecord, RetrievedChunk


@dataclass(frozen=True)
class PipelineResult:
    configuration: str
    answer: str
    evidence: tuple[RetrievedChunk, ...]
    generator_backend: str
    prompt_tokens: int | None
    generated_tokens: int | None
    fallback: bool
    fallback_reason: str | None = None
    retrieval_diagnostics: dict[str, Any] | None = None
    configuration_attributes: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "configuration": self.configuration,
            "answer": self.answer,
            "evidence": [item.to_dict() for item in self.evidence],
            "evidence_ids": [item.chunk.evidence_id for item in self.evidence],
            "generator_backend": self.generator_backend,
            "prompt_tokens": self.prompt_tokens,
            "generated_tokens": self.generated_tokens,
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
            "retrieval_diagnostics": self.retrieval_diagnostics or {},
            "configuration_attributes": self.configuration_attributes or {},
        }


class ConfigurationPipeline:
    def __init__(
        self,
        index: BM25Index,
        generator: Generator,
        *,
        hybrid_index: HybridIndex | None = None,
        c1_top_k: int = 5,
        c1_candidate_k: int = 20,
        c2_top_k: int = 8,
        c2_candidate_k: int = 24,
        c2_min_evidence: int = 3,
        strict_hazard_filter: bool = True,
        configuration_library: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.index = index
        self.hybrid_index = hybrid_index
        self.generator = generator
        self.c1_top_k = c1_top_k
        self.c1_candidate_k = c1_candidate_k
        self.c2_top_k = c2_top_k
        self.c2_candidate_k = c2_candidate_k
        self.c2_min_evidence = c2_min_evidence
        self.strict_hazard_filter = strict_hazard_filter
        self.configuration_library = configuration_library or {}

    def run(self, configuration: str, query: QueryRecord) -> PipelineResult:
        diagnostics: dict[str, Any] = {
            "retrieval_profile": configuration,
            "dense_backend": (
                self.hybrid_index.encoder_backend if self.hybrid_index else None
            ),
        }
        if configuration == "C0":
            evidence: list[RetrievedChunk] = []
            fallback_reason = None
        elif configuration == "C1":
            if self.hybrid_index is None:
                raise RuntimeError("C1 requires a configured hybrid index")
            evidence = self.hybrid_index.search(
                query.text,
                self.c1_top_k,
                candidate_k=self.c1_candidate_k,
            )
            diagnostics["retrieval_steps"] = 1
            diagnostics["candidate_count"] = min(
                self.c1_candidate_k, len(self.hybrid_index.chunks)
            )
            fallback_reason = "no_applicable_protocol" if not evidence else None
        elif configuration == "C2":
            if self.hybrid_index is None:
                raise RuntimeError("C2 requires a configured hybrid index")
            first = self.hybrid_index.search(
                query.text,
                self.c2_candidate_k,
                candidate_k=self.c2_candidate_k,
            )
            applicable, rejected = filter_applicable_protocols(
                first,
                disaster_type=query.disaster_type,
                jurisdiction=str(query.metadata.get("jurisdiction", "")),
                as_of_date=str(
                    query.metadata.get(
                        "as_of_date", query.metadata.get("query_date", "")
                    )
                ),
                target_population=str(query.metadata.get("target_population", "")),
                strict_hazard=self.strict_hazard_filter,
            )
            steps = 1
            if len(applicable) < self.c2_min_evidence:
                second_query = build_second_step_query(
                    query.text, query.disaster_type
                )
                second = self.hybrid_index.search(
                    second_query,
                    self.c2_candidate_k,
                    candidate_k=self.c2_candidate_k,
                )
                second_applicable, second_rejected = filter_applicable_protocols(
                    second,
                    disaster_type=query.disaster_type,
                    jurisdiction=str(query.metadata.get("jurisdiction", "")),
                    as_of_date=str(
                        query.metadata.get(
                            "as_of_date", query.metadata.get("query_date", "")
                        )
                    ),
                    target_population=str(
                        query.metadata.get("target_population", "")
                    ),
                    strict_hazard=self.strict_hazard_filter,
                )
                applicable = merge_ranked_results(applicable, second_applicable)
                for key, value in second_rejected.items():
                    rejected[key] = rejected.get(key, 0) + value
                steps = 2
            reranked = protocol_aware_rerank(
                query.text, query.disaster_type, applicable
            )
            evidence = reranked[: self.c2_top_k]
            conflicts = detect_evidence_conflicts(evidence)
            diagnostics.update(
                {
                    "retrieval_steps": steps,
                    "candidate_count": len(first),
                    "filter_rejections": rejected,
                    "applicable_count": len(applicable),
                    "conflicts": conflicts,
                }
            )
            fallback_reason = (
                "no_applicable_protocol"
                if not evidence
                else "conflicting_evidence"
                if conflicts
                else None
            )
        elif configuration == "C3":
            evidence = []
            fallback_reason = "safe_fallback_configuration"
        else:
            raise ValueError(f"unknown configuration: {configuration}")
        if fallback_reason and configuration in {"C1", "C2", "C3"}:
            generated = GenerationResult(
                text=render_safety_fallback(query, fallback_reason),
                backend="deterministic-safety-template",
            )
        else:
            generated = self.generator.generate(
                query,
                evidence,
                configuration=configuration,
            )
        return PipelineResult(
            configuration=configuration,
            answer=generated.text,
            evidence=tuple(evidence),
            generator_backend=generated.backend,
            prompt_tokens=generated.prompt_tokens,
            generated_tokens=generated.generated_tokens,
            fallback=bool(fallback_reason),
            fallback_reason=fallback_reason,
            retrieval_diagnostics=diagnostics,
            configuration_attributes=dict(
                self.configuration_library.get(configuration, {})
            ),
        )
