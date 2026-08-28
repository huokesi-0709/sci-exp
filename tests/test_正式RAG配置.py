import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.generation import ExtractiveGenerator
from sci_exp.pipelines import ConfigurationPipeline
from sci_exp.retrieval import (
    BM25Index,
    HashingDenseEncoder,
    HybridIndex,
    detect_evidence_conflicts,
    filter_applicable_protocols,
)
from sci_exp.schemas import InferenceQuery, ProtocolChunk, QueryRecord, RetrievedChunk


def chunk(
    evidence_id: str,
    text: str,
    *,
    hazard=("fire",),
    jurisdiction="CN",
    status="current",
    effective="2024-01-01",
    expiry="",
):
    return ProtocolChunk(
        evidence_id=evidence_id,
        text=text,
        source_org="test",
        jurisdiction=jurisdiction,
        effective_date=effective,
        expiry_date=expiry,
        authority_level=5,
        hazard_types=tuple(hazard),
        applicability=("general_public",),
        status=status,
    )


class FormalRetrievalTests(unittest.TestCase):
    def test_hybrid_retrieval_combines_lexical_and_dense_rankings(self):
        chunks = [
            chunk("fire", "室内烟雾时保持低姿并沿安全出口撤离。"),
            chunk("flood", "积水道路不要驾车进入。", hazard=("flood",)),
        ]
        index = HybridIndex(chunks, HashingDenseEncoder(64))
        results = index.search("烟雾如何撤离", top_k=2)
        self.assertEqual(results[0].chunk.evidence_id, "fire")
        self.assertEqual(len({item.chunk.evidence_id for item in results}), 2)
        self.assertTrue(all(item.score > 0 for item in results))

    def test_protocol_filter_checks_hazard_area_and_date(self):
        candidates = [
            RetrievedChunk(chunk("ok", "撤离。"), 1.0, 1),
            RetrievedChunk(
                chunk("wrong_area", "撤离。", jurisdiction="US"), 0.9, 2
            ),
            RetrievedChunk(
                chunk("future", "撤离。", effective="2028-01-01"), 0.8, 3
            ),
            RetrievedChunk(
                chunk("old", "撤离。", status="withdrawn"), 0.7, 4
            ),
            RetrievedChunk(
                chunk("wrong_hazard", "撤离。", hazard=("flood",)), 0.6, 5
            ),
        ]
        kept, rejected = filter_applicable_protocols(
            candidates,
            predicted_hazard_types=("fire",),
            jurisdiction="CN-SC",
            as_of_date="2026-07-28",
        )
        self.assertEqual([item.chunk.evidence_id for item in kept], ["ok"])
        self.assertEqual(rejected["jurisdiction"], 1)
        self.assertEqual(rejected["not_yet_effective"], 1)
        self.assertEqual(rejected["status"], 1)
        self.assertEqual(rejected["hazard"], 1)

    def test_conflict_detector_flags_opposite_overlapping_directives(self):
        evidence = [
            RetrievedChunk(chunk("a", "发生火灾时应立即乘坐电梯撤离。"), 1.0, 1),
            RetrievedChunk(chunk("b", "发生火灾时不得乘坐电梯撤离。"), 0.9, 2),
        ]
        conflicts = detect_evidence_conflicts(evidence)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["status"], "candidate_requires_review")

    def test_c2_filters_and_exposes_diagnostics(self):
        chunks = [
            chunk("fire", "室内烟雾时保持低姿并沿安全出口撤离。"),
            chunk("flood", "积水道路不要驾车进入。", hazard=("flood",)),
        ]
        hybrid = HybridIndex(chunks, HashingDenseEncoder(64))
        pipeline = ConfigurationPipeline(
            BM25Index(chunks),
            ExtractiveGenerator(),
            hybrid_index=hybrid,
            c2_top_k=2,
            c2_candidate_k=2,
            c2_min_evidence=2,
        )
        query = InferenceQuery(
            query_id="q1",
            text="屋里有烟怎么撤离",
            language="zh-CN",
            metadata={"jurisdiction": "CN-SC", "as_of_date": "2026-07-28"},
        )
        result = pipeline.run("C2", query)
        self.assertEqual(
            {item.chunk.evidence_id for item in result.evidence}, {"fire", "flood"}
        )
        self.assertFalse(result.retrieval_diagnostics["gold_label_access"])
        self.assertEqual(
            result.retrieval_diagnostics["hazard_filter_source"],
            "disabled_no_inference_time_predictor",
        )

    def test_c3_is_deterministic_template_without_evidence(self):
        chunks = [chunk("fire", "火灾时撤离。")]
        hybrid = HybridIndex(chunks, HashingDenseEncoder(64))
        pipeline = ConfigurationPipeline(
            BM25Index(chunks),
            ExtractiveGenerator(),
            hybrid_index=hybrid,
        )
        query = InferenceQuery("q", "怎么办", "zh-CN")
        first = pipeline.run("C3", query)
        second = pipeline.run("C3", query)
        self.assertEqual(first.answer, second.answer)
        self.assertTrue(first.fallback)
        self.assertEqual(first.generator_backend, "deterministic-safety-template")
        self.assertEqual(first.evidence, ())

    def test_gold_labels_do_not_change_retrieval(self):
        chunks = [
            chunk("a", "烟雾时低姿撤离。"),
            chunk("b", "火灾时不要乘坐电梯。"),
        ]
        hybrid = HybridIndex(chunks, HashingDenseEncoder(64))
        pipeline = ConfigurationPipeline(
            BM25Index(chunks),
            ExtractiveGenerator(),
            hybrid_index=hybrid,
        )
        common = dict(
            text="烟雾怎么撤离",
            language="zh-CN",
        )
        left = QueryRecord(
            query_id="same",
            disaster_type="fire",
            query_type="single",
            risk_level=3,
            should_fallback=False,
            gold_evidence_ids=("a",),
            required_actions=("低姿撤离",),
            prohibited_actions=("乘坐电梯",),
            **common,
        )
        right = QueryRecord(
            query_id="same",
            disaster_type="flood",
            query_type="out_of_scope",
            risk_level=0,
            should_fallback=True,
            gold_evidence_ids=("b",),
            required_actions=("远离积水",),
            prohibited_actions=("低姿撤离",),
            **common,
        )
        self.assertEqual(
            pipeline.run("C2", left.to_inference_query()).to_dict(),
            pipeline.run("C2", right.to_inference_query()).to_dict(),
        )

    def test_pipeline_rejects_annotated_query_record(self):
        chunks = [chunk("a", "烟雾时低姿撤离。")]
        pipeline = ConfigurationPipeline(
            BM25Index(chunks),
            ExtractiveGenerator(),
            hybrid_index=HybridIndex(chunks, HashingDenseEncoder(64)),
        )
        annotated = QueryRecord(
            "q", "烟雾怎么撤离", "fire", "single", 3, "zh-CN", False
        )
        with self.assertRaises(TypeError):
            pipeline.run("C2", annotated)  # type: ignore[arg-type]

    def test_formal_manifest_and_dense_weight_hash_are_consistent(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads(
            (root / "configs" / "正式配置清单_v1.0.json").read_text(encoding="utf-8")
        )
        weight = (
            root
            / "models"
            / "embedding"
            / "bge-small-zh-v1.5"
            / "model.safetensors"
        )
        actual = hashlib.sha256(weight.read_bytes()).hexdigest()
        self.assertEqual(actual, manifest["dense_encoder"]["formal_weight_sha256"])
        self.assertFalse(
            manifest["publication_gates"]["formal_dense_backend_loads"]
        )
        self.assertEqual(
            set(manifest["configurations"]), {"C0", "C1", "C2", "C3"}
        )


if __name__ == "__main__":
    unittest.main()
