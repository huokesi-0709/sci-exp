from __future__ import annotations

import os
import platform
import random
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import project_path
from .evaluation import evaluate_result
from .energy_model import load_energy_predictor
from .features import query_features
from .generation import make_generator
from .io_utils import read_json, write_jsonl
from .pipelines import ConfigurationPipeline
from .retrieval import BM25Index, HybridIndex, make_dense_encoder
from .risk_model import LogisticRiskPredictor
from .router import SafetyConstrainedRouter, SoftWeightingRouter
from .schemas import ProtocolChunk, QueryRecord
from .telemetry import TelemetrySampler, read_sample


def build_pipeline(
    config: dict[str, Any],
    protocols: list[ProtocolChunk],
) -> ConfigurationPipeline:
    retrieval = config.get("retrieval", {})
    lexical = BM25Index(protocols)
    hybrid = HybridIndex(
        protocols,
        make_dense_encoder(retrieval),
        lexical_weight=float(retrieval.get("lexical_weight", 1.0)),
        dense_weight=float(retrieval.get("dense_weight", 1.0)),
        rrf_k=int(retrieval.get("rrf_k", 60)),
    )
    return ConfigurationPipeline(
        lexical,
        make_generator(config.get("generator", {})),
        hybrid_index=hybrid,
        c1_top_k=int(retrieval.get("c1_top_k", 5)),
        c1_candidate_k=int(retrieval.get("c1_candidate_k", 20)),
        c2_top_k=int(retrieval.get("c2_top_k", 8)),
        c2_candidate_k=int(retrieval.get("c2_candidate_k", 24)),
        c2_min_evidence=int(retrieval.get("c2_min_evidence", 3)),
        strict_hazard_filter=bool(retrieval.get("strict_hazard_filter", True)),
        configuration_library={
            str(key): dict(value)
            for key, value in config.get("configuration_library", {}).items()
        },
    )


def run_exhaustive(
    config: dict[str, Any],
    protocols: list[ProtocolChunk],
    queries: Iterable[QueryRecord],
    *,
    output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    experiment = config.get("experiment", {})
    configurations = [str(item) for item in experiment.get("configs", ["C0", "C1", "C2", "C3"])]
    repetitions = int(experiment.get("repetitions", 1))
    seed = int(experiment.get("seed", 42))
    tasks = [
        (query, configuration, repetition)
        for repetition in range(repetitions)
        for query in queries
        for configuration in configurations
    ]
    random.Random(seed).shuffle(tasks)
    pipeline = build_pipeline(config, protocols)
    telemetry_config = _resolved_telemetry_config(config.get("telemetry", {}))
    rows = [
        _run_one(
            pipeline,
            query,
            configuration,
            repetition,
            telemetry_config,
            run_order=run_order,
        )
        for run_order, (query, configuration, repetition) in enumerate(tasks, 1)
    ]
    target = output_path or experiment.get("output", "results/runs.jsonl")
    write_jsonl(project_path(config, target), rows)
    return rows


def run_routed(
    config: dict[str, Any],
    protocols: list[ProtocolChunk],
    queries: Iterable[QueryRecord],
    *,
    output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    pipeline = build_pipeline(config, protocols)
    router = _build_router(config)
    telemetry_config = _resolved_telemetry_config(config.get("telemetry", {}))
    repetitions = int(config.get("experiment", {}).get("repetitions", 1))
    seed = int(config.get("experiment", {}).get("seed", 42))
    tasks = [
        (query, repetition)
        for repetition in range(repetitions)
        for query in queries
    ]
    random.Random(seed).shuffle(tasks)
    rows: list[dict[str, Any]] = []
    for run_order, (query, repetition) in enumerate(tasks, 1):
        row = _run_one(
            pipeline,
            query,
            None,
            repetition,
            telemetry_config,
            run_order=run_order,
            router=router,
        )
        rows.append(row)
    target = output_path or config.get("experiment", {}).get(
        "routed_output",
        "results/routed_runs.jsonl",
    )
    write_jsonl(project_path(config, target), rows)
    return rows


def _build_router(config: dict[str, Any]) -> Any:
    router_config = config.get("router", {})
    thresholds = router_config.get("thresholds")
    thresholds_file = router_config.get("thresholds_file")
    if thresholds_file:
        thresholds_value = read_json(project_path(config, thresholds_file))
        thresholds = thresholds_value["thresholds"]
    if not thresholds:
        raise ValueError("router requires inline thresholds or thresholds_file")
    predictor = None
    model_file = router_config.get("risk_model_file")
    if model_file:
        predictor = LogisticRiskPredictor(read_json(project_path(config, model_file)))
    resource_profile = {}
    resource_file = router_config.get("resource_profile_file")
    if resource_file:
        resource_profile = read_json(project_path(config, resource_file))
    energy_predictor = None
    energy_model_file = router_config.get("energy_model_file")
    if energy_model_file:
        energy_predictor = load_energy_predictor(
            project_path(config, energy_model_file)
        )
    energy_budget = router_config.get("energy_budget_j")
    energy_budget_env = str(
        router_config.get("energy_budget_env", "SCI_EXP_ENERGY_BUDGET_J")
    ).strip()
    if energy_budget_env and os.environ.get(energy_budget_env, "").strip():
        energy_budget = float(os.environ[energy_budget_env])
    base_router = SafetyConstrainedRouter(
        thresholds=thresholds,
        predicted_energy_j=resource_profile.get(
            "predicted_energy_j",
            router_config.get("predicted_energy_j", {}),
        ),
        predicted_latency_ms=resource_profile.get(
            "predicted_latency_ms",
            router_config.get("predicted_latency_ms", {}),
        ),
        predicted_memory_mb=resource_profile.get(
            "predicted_memory_mb",
            router_config.get("predicted_memory_mb"),
        ),
        memory_budget_mb=float(router_config.get("memory_budget_mb", 4096)),
        latency_budget_ms=float(router_config.get("latency_budget_ms", 30000)),
        risk_predictor=predictor,
        energy_predictor=energy_predictor,
        energy_budget_j=(
            float(energy_budget) if energy_budget is not None else None
        ),
        memory_headroom_fraction=float(
            router_config.get("memory_headroom_fraction", 0.9)
        ),
    )
    if str(router_config.get("policy", "hard_safety")) == "soft_weighting":
        return SoftWeightingRouter(
            base_router,
            risk_weight=float(router_config.get("soft_risk_weight", 0.8)),
        )
    return base_router


def _routing_state() -> dict[str, float | None]:
    sample = read_sample([], 1.0)
    return {
        "device_temperature_c_start": sample.temperature_c,
        "available_memory_mb_min": sample.available_memory_mb,
        "load_1m_peak": sample.load_1m,
        "cpu_frequency_mhz_start": sample.cpu_frequency_mhz,
        "cpu_frequency_mhz_min": sample.cpu_frequency_mhz,
        "cooling_state_peak": sample.cooling_state,
        # SHT31 lives on the independent meter and is merged after the run.  It
        # must not be fabricated from SoC temperature at routing time.
        "ambient_temperature_c_start": None,
        "ambient_relative_humidity_pct_start": None,
    }


def _resolved_telemetry_config(value: dict[str, Any]) -> dict[str, Any]:
    telemetry = dict(value)
    external = dict(telemetry.get("external_meter", {}))
    host_env = str(external.get("marker_host_env", "")).strip()
    if host_env:
        external["marker_host"] = os.environ.get(
            host_env, str(external.get("marker_host", ""))
        ).strip()
    if external.get("required_for_formal_run") and not external.get("marker_host"):
        raise RuntimeError(
            "formal run requires external power meter marker host; set "
            f"{host_env or 'telemetry.external_meter.marker_host'}"
        )
    telemetry["external_meter"] = external
    return telemetry


def _run_one(
    pipeline: ConfigurationPipeline,
    query: QueryRecord,
    configuration: str | None,
    repetition: int,
    telemetry_config: dict[str, Any],
    *,
    run_order: int,
    router: SafetyConstrainedRouter | None = None,
) -> dict[str, Any]:
    sampler = TelemetrySampler(
        interval_seconds=float(telemetry_config.get("sample_interval_seconds", 0.1)),
        power_paths=[str(item) for item in telemetry_config.get("power_paths", [])],
        power_scale=float(telemetry_config.get("power_scale", 0.000001)),
        external_marker_host=str(
            telemetry_config.get("external_meter", {}).get("marker_host", "")
        ),
        external_marker_port=int(
            telemetry_config.get("external_meter", {}).get("marker_port", 8765)
        ),
    )
    started_at = datetime.now(timezone.utc).isoformat()
    requested_configuration = configuration or "ROUTED"
    run_key = f"{query.query_id}:{requested_configuration}:{repetition}"
    marker_payload = {
        "run_key": run_key,
        "query_id": query.query_id,
        "configuration": requested_configuration,
        "repetition": repetition,
        "run_order": run_order,
    }
    sampler.start()
    sampler.mark("query_start", marker_payload)
    start = time.perf_counter()
    try:
        routing = None
        routing_overhead_ms = 0.0
        if router is not None:
            routing_state = _routing_state()
            routing_started = time.perf_counter()
            decision = router.select(query, routing_state)
            routing_overhead_ms = (time.perf_counter() - routing_started) * 1000.0
            routing = decision.to_dict()
            routing["state_at_decision"] = routing_state
            configuration = decision.configuration
        if configuration is None:
            raise RuntimeError("configuration was not selected")
        result = pipeline.run(configuration, query)
        latency_ms = (time.perf_counter() - start) * 1000.0
        sampler.mark("query_end", marker_payload)
        telemetry = sampler.stop()
        row = {
            "schema_version": "2.0",
            "status": "ok",
            "started_at_utc": started_at,
            "host": platform.node(),
            "platform": platform.platform(),
            "query_id": query.query_id,
            "run_key": run_key,
            "run_order": run_order,
            "source_group_id": query.source_group_id,
            "split": query.split,
            "repetition": repetition,
            "latency_ms": latency_ms,
            "routing_overhead_ms": routing_overhead_ms,
            "query_features": query_features(query),
            **result.to_dict(),
            "metrics": evaluate_result(query, result),
            "telemetry": telemetry,
        }
        if routing is not None:
            row["routing"] = routing
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        sampler.mark("query_end", {**marker_payload, "run_status": "error"})
        telemetry = sampler.stop()
        row = {
            "schema_version": "2.0",
            "status": "error",
            "started_at_utc": started_at,
            "host": platform.node(),
            "platform": platform.platform(),
            "query_id": query.query_id,
            "run_key": run_key,
            "run_order": run_order,
            "source_group_id": query.source_group_id,
            "split": query.split,
            "configuration": configuration,
            "repetition": repetition,
            "latency_ms": latency_ms,
            "routing_overhead_ms": (
                routing_overhead_ms if "routing_overhead_ms" in locals() else None
            ),
            "telemetry": telemetry,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    return row
