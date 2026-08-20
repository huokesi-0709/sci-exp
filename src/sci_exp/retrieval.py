from __future__ import annotations

import math
import re
from datetime import date
from collections import Counter
from dataclasses import replace
from hashlib import blake2b
from typing import Protocol, Sequence

from .schemas import ProtocolChunk, RetrievedChunk


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """A deterministic tokenizer that works without native dependencies."""
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


class BM25Index:
    def __init__(
        self,
        chunks: list[ProtocolChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if not chunks:
            raise ValueError("BM25Index requires at least one protocol chunk")
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self._term_frequencies = [Counter(tokenize(chunk.text)) for chunk in chunks]
        self._lengths = [sum(counts.values()) for counts in self._term_frequencies]
        self._average_length = sum(self._lengths) / len(self._lengths)
        document_frequency: Counter[str] = Counter()
        for counts in self._term_frequencies:
            document_frequency.update(counts.keys())
        count = len(chunks)
        self._idf = {
            term: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if top_k <= 0:
            return []
        query_terms = tokenize(query)
        scored: list[tuple[float, str, int]] = []
        for index, counts in enumerate(self._term_frequencies):
            score = 0.0
            document_length = self._lengths[index]
            normalizer = self.k1 * (
                1.0 - self.b + self.b * document_length / max(self._average_length, 1.0)
            )
            for term in query_terms:
                frequency = counts.get(term, 0)
                if frequency:
                    score += self._idf.get(term, 0.0) * (
                        frequency * (self.k1 + 1.0) / (frequency + normalizer)
                    )
            scored.append((score, self.chunks[index].evidence_id, index))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            RetrievedChunk(chunk=self.chunks[index], score=score, rank=rank)
            for rank, (score, _, index) in enumerate(scored[:top_k], start=1)
        ]


class DenseEncoder(Protocol):
    """Minimal interface shared by local sentence encoders and test encoders."""

    backend_name: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashingDenseEncoder:
    """Dependency-free development encoder.

    It exists so retrieval/filtering code can be verified on Windows. It is not
    the formal semantic encoder and must never be reported as one.
    """

    backend_name = "hashing-development-only"

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 32:
            raise ValueError("dimensions must be at least 32")
        self.dimensions = dimensions

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._encode_one(text) for text in texts]

    def _encode_one(self, text: str) -> list[float]:
        compact = re.sub(r"\s+", "", text.lower())
        features = tokenize(text)
        features.extend(
            compact[index : index + 2]
            for index in range(max(0, len(compact) - 1))
        )
        vector = [0.0] * self.dimensions
        for feature in features:
            digest = blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector


class SentenceTransformerEncoder:
    """Local-only sentence-transformers adapter; no model is downloaded here."""

    backend_name = "sentence-transformers-local"

    def __init__(self, model_path: str, *, device: str = "cpu") -> None:
        if not model_path:
            raise ValueError("sentence-transformers backend requires a local model_path")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for the formal dense backend"
            ) from exc
        self.model = SentenceTransformer(model_path, device=device)

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        values = self.model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [[float(item) for item in row] for row in values]


class DenseIndex:
    def __init__(self, chunks: list[ProtocolChunk], encoder: DenseEncoder) -> None:
        if not chunks:
            raise ValueError("DenseIndex requires at least one protocol chunk")
        self.chunks = list(chunks)
        self.encoder = encoder
        self._embeddings = encoder.encode([chunk.text for chunk in chunks])
        if len(self._embeddings) != len(self.chunks):
            raise ValueError("dense encoder returned the wrong number of embeddings")

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if top_k <= 0:
            return []
        query_vector = self.encoder.encode([query])[0]
        scored = [
            (
                sum(left * right for left, right in zip(query_vector, embedding)),
                chunk.evidence_id,
                index,
            )
            for index, (chunk, embedding) in enumerate(
                zip(self.chunks, self._embeddings)
            )
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            RetrievedChunk(chunk=self.chunks[index], score=score, rank=rank)
            for rank, (score, _, index) in enumerate(scored[:top_k], start=1)
        ]


class HybridIndex:
    """BM25+dense retrieval fused with weighted reciprocal-rank fusion."""

    def __init__(
        self,
        chunks: list[ProtocolChunk],
        encoder: DenseEncoder,
        *,
        lexical_weight: float = 1.0,
        dense_weight: float = 1.0,
        rrf_k: int = 60,
    ) -> None:
        self.chunks = list(chunks)
        self.lexical = BM25Index(chunks)
        self.dense = DenseIndex(chunks, encoder)
        self.encoder_backend = encoder.backend_name
        self.lexical_weight = lexical_weight
        self.dense_weight = dense_weight
        self.rrf_k = rrf_k

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        candidate_k: int | None = None,
    ) -> list[RetrievedChunk]:
        if top_k <= 0:
            return []
        depth = max(top_k, candidate_k or top_k)
        lexical = self.lexical.search(query, depth)
        dense = self.dense.search(query, depth)
        chunks: dict[str, ProtocolChunk] = {}
        scores: Counter[str] = Counter()
        for result in lexical:
            evidence_id = result.chunk.evidence_id
            chunks[evidence_id] = result.chunk
            scores[evidence_id] += self.lexical_weight / (self.rrf_k + result.rank)
        for result in dense:
            evidence_id = result.chunk.evidence_id
            chunks[evidence_id] = result.chunk
            scores[evidence_id] += self.dense_weight / (self.rrf_k + result.rank)
        ranked = sorted(scores, key=lambda item: (-scores[item], item))[:top_k]
        return [
            RetrievedChunk(chunks[evidence_id], scores[evidence_id], rank)
            for rank, evidence_id in enumerate(ranked, start=1)
        ]


def make_dense_encoder(config: dict[str, object]) -> DenseEncoder:
    backend = str(config.get("dense_backend", "hashing_development"))
    if backend == "hashing_development":
        return HashingDenseEncoder(int(config.get("hashing_dimensions", 384)))
    if backend == "sentence_transformers_local":
        return SentenceTransformerEncoder(
            str(config.get("dense_model_path", "")),
            device=str(config.get("dense_device", "cpu")),
        )
    raise ValueError(f"unsupported dense backend: {backend}")


def filter_applicable_protocols(
    candidates: list[RetrievedChunk],
    *,
    disaster_type: str,
    jurisdiction: str = "",
    as_of_date: str = "",
    target_population: str = "",
    strict_hazard: bool = True,
) -> tuple[list[RetrievedChunk], dict[str, int]]:
    """Apply inference-time protocol status, date, area and population gates."""

    kept: list[RetrievedChunk] = []
    rejected: Counter[str] = Counter()
    query_date = _parse_date(as_of_date)
    for candidate in candidates:
        chunk = candidate.chunk
        status = chunk.status.lower()
        if any(
            marker in status
            for marker in ("obsolete", "withdrawn", "expired", "revoked", "draft")
        ):
            rejected["status"] += 1
            continue
        if strict_hazard and chunk.hazard_types:
            allowed_hazards = set(chunk.hazard_types)
            if (
                disaster_type not in allowed_hazards
                and "all_hazards" not in allowed_hazards
                and "general_emergency" not in allowed_hazards
            ):
                rejected["hazard"] += 1
                continue
        if jurisdiction and not _jurisdiction_applies(chunk.jurisdiction, jurisdiction):
            rejected["jurisdiction"] += 1
            continue
        if query_date:
            effective = _parse_date(chunk.effective_date)
            expiry = _parse_date(chunk.expiry_date)
            if effective and effective > query_date:
                rejected["not_yet_effective"] += 1
                continue
            if expiry and expiry < query_date:
                rejected["expired"] += 1
                continue
        if (
            target_population
            and chunk.target_population
            and chunk.target_population not in {"general_public", target_population}
        ):
            rejected["target_population"] += 1
            continue
        kept.append(candidate)
    return kept, dict(rejected)


def merge_ranked_results(
    first: list[RetrievedChunk],
    second: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    by_id: dict[str, RetrievedChunk] = {}
    for item in first + second:
        existing = by_id.get(item.chunk.evidence_id)
        if existing is None or item.score > existing.score:
            by_id[item.chunk.evidence_id] = item
    ordered = sorted(
        by_id.values(),
        key=lambda item: (-item.score, item.chunk.evidence_id),
    )
    return [replace(item, rank=rank) for rank, item in enumerate(ordered, start=1)]


def build_second_step_query(query: str, disaster_type: str) -> str:
    hints = {
        "flood": "洪水 内涝 溺水 避险 救援",
        "fire": "火灾 烟雾 撤离 灭火 报警",
        "earthquake": "地震 余震 避险 撤离",
        "typhoon": "台风 暴雨 大风 避险",
        "poisoning": "中毒 急救 现场安全",
        "heatwave": "高温 中暑 急救",
    }
    return f"{query} {hints.get(disaster_type, disaster_type)}"


def detect_evidence_conflicts(
    evidence: list[RetrievedChunk],
) -> list[dict[str, object]]:
    """Flag plausible positive/negative instruction conflicts for human review."""

    clauses: list[tuple[RetrievedChunk, str, bool, set[str]]] = []
    for item in evidence:
        for clause in re.split(r"[。！？；\n]+", item.chunk.text):
            compact = re.sub(r"\s+", "", clause)
            if len(compact) < 4:
                continue
            tokens = set(tokenize(compact))
            negative = any(
                marker in compact
                for marker in ("不得", "不要", "禁止", "避免", "切勿", "不可", "不能")
            )
            clauses.append((item, compact, negative, tokens))
    conflicts: list[dict[str, object]] = []
    for left_index, left in enumerate(clauses):
        for right in clauses[left_index + 1 :]:
            if left[0].chunk.evidence_id == right[0].chunk.evidence_id:
                continue
            if left[2] == right[2]:
                continue
            union = left[3] | right[3]
            overlap = len(left[3] & right[3]) / len(union) if union else 0.0
            if overlap < 0.45:
                continue
            conflicts.append(
                {
                    "left_evidence_id": left[0].chunk.evidence_id,
                    "right_evidence_id": right[0].chunk.evidence_id,
                    "left_clause": left[1],
                    "right_clause": right[1],
                    "token_jaccard": round(overlap, 4),
                    "status": "candidate_requires_review",
                }
            )
    return conflicts


def protocol_aware_rerank(
    query: str,
    disaster_type: str,
    candidates: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    """Re-rank by lexical score plus protocol validity and applicability metadata."""
    query_tokens = set(tokenize(query))
    rescored: list[tuple[float, str, RetrievedChunk]] = []
    for candidate in candidates:
        chunk = candidate.chunk
        status_bonus = 0.35 if chunk.status in {"current", "demo"} else -1.0
        authority_bonus = min(max(chunk.authority_level, 0), 5) * 0.08
        hazard_bonus = 0.45 if disaster_type in chunk.hazard_types else 0.0
        applicability_tokens = set(
            token
            for value in chunk.applicability
            for token in tokenize(value)
        )
        applicability_bonus = 0.06 * len(query_tokens & applicability_tokens)
        score = (
            candidate.score
            + status_bonus
            + authority_bonus
            + hazard_bonus
            + applicability_bonus
        )
        rescored.append((score, chunk.evidence_id, candidate))
    rescored.sort(key=lambda item: (-item[0], item[1]))
    return [
        replace(candidate, score=score, rank=rank)
        for rank, (score, _, candidate) in enumerate(rescored, start=1)
    ]


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _jurisdiction_applies(protocol_area: str, query_area: str) -> bool:
    protocol = protocol_area.strip().upper()
    query = query_area.strip().upper()
    if not protocol or protocol in {"GLOBAL", "ALL"}:
        return True
    if protocol == query:
        return True
    # A national protocol applies to a subnational query such as CN-SC.
    return query.startswith(f"{protocol}-")
