from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .calibration import select_threshold
from .config import load_config, project_path
from .io_utils import read_json, read_jsonl, write_json, write_jsonl
from .ingestion import prepare_protocols
from .preprocessing import (
    preprocess_query_rows,
    preprocess_resource_rows,
    sha256_bytes,
)
from .risk_model import (
    LogisticRiskPredictor,
    score_experiment_rows,
    train_logistic_risk_models,
)
from .resource_model import build_resource_profile
from .runner import run_exhaustive, run_routed
from .schemas import InferenceQuery, ProtocolChunk, QueryRecord
from .splitting import group_split
from .telemetry import device_info
from .validation import (
    dataset_summary,
    validate_no_group_leakage,
    validate_protocols,
    validate_queries,
)


def _send_collector_stop(args: argparse.Namespace) -> dict[str, Any]:
    host = str(args.collector_host or os.environ.get("SCI_EXP_METER_HOST", ""))
    if not host:
        raise RuntimeError(
            "--stop-collector-on-exit requires --collector-host or "
            "SCI_EXP_METER_HOST"
        )
    event = "collector_stop"
    run_key = str(args.session_id or "experiment_runner_exit")
    value = {
        "schema": "ina226-marker-v1.0",
        "event": event,
        "run_key": run_key,
        "query_id": "",
        "configuration": "",
        "repetition": 0,
        "sender_epoch_ns": time.time_ns(),
        "sender_monotonic_ns": time.monotonic_ns(),
        "reason": "experiment_runner_exit",
    }
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, int(args.collector_stop_retries) + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(float(args.collector_stop_timeout))
                client.sendto(payload, (host, int(args.collector_port)))
                acknowledgement, _ = client.recvfrom(4096)
            ack = json.loads(acknowledgement.decode("utf-8"))
            if (
                not isinstance(ack, dict)
                or ack.get("type") != "marker_ack"
                or ack.get("event") != event
                or ack.get("run_key") != run_key
                or ack.get("collector_stopping") is not True
            ):
                raise RuntimeError("功率采集器返回了不匹配的停止ACK")
            return {
                "status": "acknowledged",
                "attempt": attempt,
                "host": host,
                "port": int(args.collector_port),
                "event": event,
                "run_key": run_key,
            }
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt < int(args.collector_stop_retries):
                time.sleep(1.0)
    raise RuntimeError(
        f"collector stop was not acknowledged after "
        f"{args.collector_stop_retries} attempts: {last_error}"
    )


def _load_protocols(path: Path) -> list[ProtocolChunk]:
    return [ProtocolChunk.from_dict(row) for row in read_jsonl(path)]


def _load_queries(path: Path) -> list[QueryRecord]:
    return [QueryRecord.from_dict(row) for row in read_jsonl(path)]


def _load_inference_queries(path: Path) -> list[InferenceQuery]:
    return [InferenceQuery.from_dict(row) for row in read_jsonl(path)]


def _configured_data(
    config: dict[str, Any],
) -> tuple[list[ProtocolChunk], list[QueryRecord | InferenceQuery]]:
    data = config.get("data", {})
    protocols = _load_protocols(project_path(config, data["protocols"]))
    query_path = project_path(config, data["queries"])
    query_role = str(data.get("query_role", "annotated"))
    if query_role == "inference":
        queries: list[QueryRecord | InferenceQuery] = _load_inference_queries(
            query_path
        )
    elif query_role == "annotated":
        queries = _load_queries(query_path)
    else:
        raise ValueError("data.query_role must be 'annotated' or 'inference'")
    return protocols, queries


def command_validate(args: argparse.Namespace) -> int:
    protocols = _load_protocols(Path(args.protocols))
    queries = _load_queries(Path(args.queries))
    errors = [
        *validate_protocols(protocols),
        *validate_queries(queries, {item.evidence_id for item in protocols}),
        *validate_no_group_leakage(queries),
    ]
    print(json.dumps({"errors": errors, "summary": dataset_summary(queries)}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


def command_split(args: argparse.Namespace) -> int:
    queries = _load_queries(Path(args.input))
    split_queries = group_split(queries, seed=args.seed)
    output_directory = Path(args.output_directory)
    by_split: dict[str, list[dict[str, Any]]] = {}
    for query in split_queries:
        by_split.setdefault(query.split, []).append(query.to_dict())
    for split_name, rows in by_split.items():
        write_jsonl(output_directory / f"{split_name}.jsonl", rows)
    write_json(
        output_directory / "split_summary.json",
        dataset_summary(split_queries),
    )
    print(json.dumps(dataset_summary(split_queries), ensure_ascii=False, indent=2))
    return 0


def command_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.protocols:
        config.setdefault("data", {})["protocols"] = args.protocols
    if args.queries:
        config.setdefault("data", {})["queries"] = args.queries
    protocols, queries = _configured_data(config)
    errors = list(validate_protocols(protocols))
    if queries and isinstance(queries[0], QueryRecord):
        annotated_queries = [
            query for query in queries if isinstance(query, QueryRecord)
        ]
        errors.extend(
            validate_queries(
                annotated_queries,
                {item.evidence_id for item in protocols},
            )
        )
        errors.extend(validate_no_group_leakage(annotated_queries))
    if errors:
        print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    if args.command == "route":
        rows = run_routed(config, protocols, queries, output_path=args.output)
    else:
        task_manifest = (
            project_path(config, args.task_manifest)
            if args.task_manifest
            else None
        )
        rows = run_exhaustive(
            config,
            protocols,
            queries,
            output_path=args.output,
            task_manifest_path=task_manifest,
            run_order_start=args.run_order_start,
            run_order_end=args.run_order_end,
            session_id=args.session_id,
        )
    success = sum(row["status"] == "ok" for row in rows)
    default_output = (
        config["experiment"].get("routed_output", "results/routed_runs.jsonl")
        if args.command == "route"
        else config["experiment"]["output"]
    )
    result = {
        "runs": len(rows),
        "successful": success,
        "failed": len(rows) - success,
        "output": str(
            project_path(
                config,
                args.output or default_output,
            )
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if success == len(rows) else 3


def command_export_inference_queries(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output)
    queries = _load_queries(input_path)
    inference_queries = [query.to_inference_query() for query in queries]
    write_jsonl(output_path, (query.to_dict() for query in inference_queries))
    # Read the result back through the strict loader.  This makes the export
    # fail immediately if a future edit accidentally reintroduces a Gold field.
    _load_inference_queries(output_path)
    print(
        json.dumps(
            {
                "input": str(input_path.resolve()),
                "output": str(output_path.resolve()),
                "rows": len(inference_queries),
                "output_sha256": _file_sha256(output_path),
                "gold_fields_exported": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_train_risk(args: argparse.Namespace) -> int:
    model = train_logistic_risk_models(
        read_jsonl(args.input),
        iterations=args.iterations,
        learning_rate=args.learning_rate,
        l2=args.l2,
    )
    write_json(args.output, model)
    print(json.dumps(
        {
            "output": str(Path(args.output).resolve()),
            "configurations": sorted(model["models"]),
            "sample_counts": {
                key: value["n_samples"] for key, value in model["models"].items()
            },
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def command_score_risk(args: argparse.Namespace) -> int:
    predictor = LogisticRiskPredictor(read_json(args.model))
    rows = score_experiment_rows(read_jsonl(args.input), predictor)
    write_jsonl(args.output, rows)
    print(json.dumps({"output": str(Path(args.output).resolve()), "rows": len(rows)}, ensure_ascii=False, indent=2))
    return 0


def command_profile_resources(args: argparse.Namespace) -> int:
    try:
        profile = build_resource_profile(
            read_jsonl(args.input),
            require_energy=not args.allow_missing_energy,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_json(args.output, profile)
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return 0


def command_apply_adjudication(args: argparse.Namespace) -> int:
    runs = read_jsonl(args.input)
    labels = read_jsonl(args.labels)
    indexed: dict[tuple[str, str, int | None], dict[str, Any]] = {}
    for label in labels:
        key = (
            str(label["query_id"]),
            str(label["configuration"]),
            int(label["repetition"]) if "repetition" in label else None,
        )
        indexed[key] = label
    matched = 0
    for row in runs:
        exact = (
            str(row.get("query_id", "")),
            str(row.get("configuration", "")),
            int(row.get("repetition", 0)),
        )
        generic = (exact[0], exact[1], None)
        label = indexed.get(exact, indexed.get(generic))
        if label is not None:
            missing_vector = label.get("missing_action_vector", [])
            y_trigger = bool(
                label.get(
                    "y_trigger",
                    label.get("trigger_negated", False)
                    or label.get("trigger_forbidden", False)
                    or label.get("dangerous_action", False),
                )
            )
            y_miss = bool(
                label.get(
                    "y_miss",
                    any(bool(value) for value in missing_vector)
                    if isinstance(missing_vector, list)
                    else False,
                )
            )
            quality_components_present = all(
                name in label
                for name in (
                    "protocol_correct",
                    "evidence_relevant",
                    "constraint_preserved",
                    "actionable",
                )
            )
            y_quality = bool(
                label.get(
                    "y_quality",
                    (
                        label.get("protocol_correct", False)
                        and label.get("evidence_relevant", False)
                        and label.get("constraint_preserved", False)
                        and label.get("actionable", False)
                        and not label.get("dangerous_action", False)
                    )
                    if quality_components_present
                    else not bool(label.get("severe_failure", True)),
                )
            )
            row["adjudication"] = {
                "label_schema_version": "input-config-outcome-v2.0",
                "y_trigger": y_trigger,
                "y_miss": y_miss,
                "y_quality": y_quality,
                "trigger_negated": bool(label.get("trigger_negated", False)),
                "trigger_forbidden": bool(label.get("trigger_forbidden", False)),
                "dangerous_action": bool(label.get("dangerous_action", False)),
                "missing_action_vector": missing_vector,
                "protocol_correct": bool(label.get("protocol_correct", False)),
                "evidence_relevant": bool(label.get("evidence_relevant", False)),
                "constraint_preserved": bool(
                    label.get("constraint_preserved", False)
                ),
                "actionable": bool(label.get("actionable", False)),
                "error_severity": label.get("error_severity"),
                "severe_failure": bool(
                    label.get("severe_failure", y_trigger or y_miss)
                ),
                "action_completeness": label.get("action_completeness"),
                "evidence_correct": label.get("evidence_correct"),
                "notes": label.get("notes", ""),
                "adjudicator_id": label.get("adjudicator_id", ""),
            }
            matched += 1
    successful = sum(row.get("status") == "ok" for row in runs)
    if matched != successful:
        print(
            f"adjudication is incomplete: matched {matched} of {successful} successful runs",
            file=sys.stderr,
        )
        return 2
    if matched == 0:
        print("no adjudication labels matched experiment rows", file=sys.stderr)
        return 2
    write_jsonl(args.output, runs)
    print(json.dumps({"runs": len(runs), "matched": matched, "output": str(Path(args.output).resolve())}, ensure_ascii=False, indent=2))
    return 0


def command_prepare_protocols(args: argparse.Namespace) -> int:
    registry_path = Path(args.registry).resolve()
    chunks = prepare_protocols(
        read_jsonl(registry_path),
        registry_directory=registry_path.parent,
        target_characters=args.target_characters,
        overlap_characters=args.overlap_characters,
    )
    errors = validate_protocols(chunks)
    if errors:
        print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    write_jsonl(args.output, (chunk.to_dict() for chunk in chunks))
    print(json.dumps({"sources": len(read_jsonl(registry_path)), "chunks": len(chunks), "output": str(Path(args.output).resolve())}, ensure_ascii=False, indent=2))
    return 0


def command_calibrate(args: argparse.Namespace) -> int:
    rows = read_jsonl(args.input)
    if any(isinstance(row.get("risk_scores"), dict) for row in rows):
        by_head: dict[str, dict[str, list[tuple[float, bool]]]] = {}
        for row in rows:
            configuration = str(row["configuration"])
            scores = row.get("risk_scores", {})
            labels = row.get("labels", {})
            if not isinstance(scores, dict) or not isinstance(labels, dict):
                continue
            for head, score in scores.items():
                if head not in labels:
                    continue
                by_head.setdefault(str(head), {}).setdefault(
                    configuration, []
                ).append((float(score), bool(labels[head])))
        details = {
            head: {
                configuration: select_threshold(
                    values, alpha=args.alpha, delta=args.delta
                ).to_dict()
                for configuration, values in sorted(configurations.items())
            }
            for head, configurations in sorted(by_head.items())
            if head in {"trigger", "miss", "quality_failure", "combined_risk"}
        }
        value = {
            "schema_version": "multi-head-calibration-v2.0",
            "alpha": args.alpha,
            "delta": args.delta,
            "thresholds": {
                head: {
                    configuration: result["threshold"]
                    for configuration, result in configurations.items()
                }
                for head, configurations in details.items()
            },
            "details": details,
        }
        write_json(args.output, value)
        print(json.dumps(details, ensure_ascii=False, indent=2))
        return 0
    by_configuration: dict[str, list[tuple[float, bool]]] = {}
    for row in rows:
        configuration = str(row["configuration"])
        by_configuration.setdefault(configuration, []).append(
            (float(row["risk_score"]), bool(row["failure"]))
        )
    results = {
        configuration: select_threshold(values, alpha=args.alpha, delta=args.delta).to_dict()
        for configuration, values in sorted(by_configuration.items())
    }
    write_json(
        args.output,
        {
            "alpha": args.alpha,
            "delta": args.delta,
            "thresholds": {
                configuration: value["threshold"]
                for configuration, value in results.items()
            },
            "details": results,
        },
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def command_device_info(args: argparse.Namespace) -> int:
    value = device_info()
    if args.output:
        write_json(args.output, value)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


def _file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _write_preprocess_outputs(
    result: Any,
    *,
    input_path: Path,
    output_path: Path,
    quarantine_path: Path,
    events_path: Path,
    report_path: Path,
) -> None:
    write_jsonl(output_path, result.records)
    write_jsonl(quarantine_path, result.quarantine)
    write_jsonl(events_path, result.events)
    report = dict(result.report)
    report.update(
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "input": {
                "path": str(input_path.resolve()),
                "sha256": _file_sha256(input_path),
            },
            "outputs": {
                "records": {
                    "path": str(output_path.resolve()),
                    "sha256": _file_sha256(output_path),
                },
                "quarantine": {
                    "path": str(quarantine_path.resolve()),
                    "sha256": _file_sha256(quarantine_path),
                },
                "events": {
                    "path": str(events_path.resolve()),
                    "sha256": _file_sha256(events_path),
                },
            },
        }
    )
    write_json(report_path, report)


def command_preprocess_queries(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_directory = Path(args.output_directory)
    result = preprocess_query_rows(
        read_jsonl(input_path),
        seed=args.seed,
        min_characters=args.min_characters,
        max_characters=args.max_characters,
        augment_train_copies=args.augment_train_copies,
        preserve_existing_splits=args.preserve_existing_splits,
    )
    processed_path = output_directory / "processed" / "queries.cleaned.jsonl"
    quarantine_path = (
        output_directory / "quarantine" / "queries.quarantine.jsonl"
    )
    events_path = output_directory / "logs" / "query_preprocess_events.jsonl"
    report_path = output_directory / "logs" / "query_preprocess_report.json"
    _write_preprocess_outputs(
        result,
        input_path=input_path,
        output_path=processed_path,
        quarantine_path=quarantine_path,
        events_path=events_path,
        report_path=report_path,
    )
    by_split: dict[str, list[dict[str, Any]]] = {}
    for row in result.records:
        by_split.setdefault(str(row["split"]), []).append(row)
    for split_name, rows in by_split.items():
        write_jsonl(output_directory / "splits" / f"{split_name}.jsonl", rows)
    split_hashes = {
        split_name: _file_sha256(
            output_directory / "splits" / f"{split_name}.jsonl"
        )
        for split_name in sorted(by_split)
    }
    split_manifest = {
        "schema_version": "1.0",
        "seed": args.seed,
        "input_sha256": _file_sha256(input_path),
        "split_sha256": split_hashes,
        "counts": {
            split_name: len(rows) for split_name, rows in sorted(by_split.items())
        },
    }
    write_json(
        output_directory / "splits" / "split_manifest.json",
        split_manifest,
    )
    summary = {
        "output": str(processed_path.resolve()),
        "report": str(report_path.resolve()),
        **result.report["counts"],
        "splits": result.report["summary"]["split"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.fail_on_quarantine and result.quarantine:
        return 2
    return 0


def command_preprocess_runs(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output)
    stem = output_path.stem
    result = preprocess_resource_rows(
        read_jsonl(input_path),
        require_energy=not args.allow_missing_energy,
        robust_z_threshold=args.robust_z_threshold,
    )
    quarantine_path = output_path.parent / f"{stem}.quarantine.jsonl"
    events_path = output_path.parent / f"{stem}.events.jsonl"
    report_path = output_path.parent / f"{stem}.report.json"
    _write_preprocess_outputs(
        result,
        input_path=input_path,
        output_path=output_path,
        quarantine_path=quarantine_path,
        events_path=events_path,
        report_path=report_path,
    )
    summary = {
        "output": str(output_path.resolve()),
        "report": str(report_path.resolve()),
        **result.report["counts"],
        "outlier_flags": result.report["outlier_flags"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.fail_on_quarantine and result.quarantine:
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline emergency RAG experiment runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", aliases=["smoke"])
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--output")
    run_parser.add_argument("--protocols")
    run_parser.add_argument("--queries")
    run_parser.add_argument(
        "--task-manifest",
        help="frozen exhaustive task manifest; enables strict formal batch mode",
    )
    run_parser.add_argument("--run-order-start", type=int)
    run_parser.add_argument("--run-order-end", type=int)
    run_parser.add_argument("--session-id", default="")
    run_parser.add_argument(
        "--stop-collector-on-exit",
        action="store_true",
        help="always request a graceful Windows collector stop when this run exits",
    )
    run_parser.add_argument("--collector-host", default="")
    run_parser.add_argument("--collector-port", type=int, default=8765)
    run_parser.add_argument("--collector-stop-timeout", type=float, default=2.0)
    run_parser.add_argument("--collector-stop-retries", type=int, default=3)
    run_parser.set_defaults(handler=command_run)

    route_parser = subparsers.add_parser("route")
    route_parser.add_argument("--config", required=True)
    route_parser.add_argument("--output")
    route_parser.add_argument("--protocols")
    route_parser.add_argument("--queries")
    route_parser.set_defaults(handler=command_run)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--protocols", required=True)
    validate_parser.add_argument("--queries", required=True)
    validate_parser.set_defaults(handler=command_validate)

    split_parser = subparsers.add_parser("split")
    split_parser.add_argument("--input", required=True)
    split_parser.add_argument("--output-directory", required=True)
    split_parser.add_argument("--seed", type=int, default=42)
    split_parser.set_defaults(handler=command_split)

    export_inference_parser = subparsers.add_parser("export-inference-queries")
    export_inference_parser.add_argument("--input", required=True)
    export_inference_parser.add_argument("--output", required=True)
    export_inference_parser.set_defaults(handler=command_export_inference_queries)

    calibration_parser = subparsers.add_parser("calibrate")
    calibration_parser.add_argument("--input", required=True)
    calibration_parser.add_argument("--output", required=True)
    calibration_parser.add_argument("--alpha", type=float, default=0.05)
    calibration_parser.add_argument("--delta", type=float, default=0.05)
    calibration_parser.set_defaults(handler=command_calibrate)

    device_parser = subparsers.add_parser("device-info")
    device_parser.add_argument("--output")
    device_parser.set_defaults(handler=command_device_info)

    train_parser = subparsers.add_parser("train-risk")
    train_parser.add_argument("--input", required=True)
    train_parser.add_argument("--output", required=True)
    train_parser.add_argument("--iterations", type=int, default=1200)
    train_parser.add_argument("--learning-rate", type=float, default=0.1)
    train_parser.add_argument("--l2", type=float, default=0.01)
    train_parser.set_defaults(handler=command_train_risk)

    score_parser = subparsers.add_parser("score-risk")
    score_parser.add_argument("--input", required=True)
    score_parser.add_argument("--model", required=True)
    score_parser.add_argument("--output", required=True)
    score_parser.set_defaults(handler=command_score_risk)

    profile_parser = subparsers.add_parser("profile-resources")
    profile_parser.add_argument("--input", required=True)
    profile_parser.add_argument("--output", required=True)
    profile_parser.add_argument(
        "--allow-missing-energy",
        action="store_true",
        help="development only; formal energy optimization requires physical measurements",
    )
    profile_parser.set_defaults(handler=command_profile_resources)

    adjudication_parser = subparsers.add_parser("apply-adjudication")
    adjudication_parser.add_argument("--input", required=True)
    adjudication_parser.add_argument("--labels", required=True)
    adjudication_parser.add_argument("--output", required=True)
    adjudication_parser.set_defaults(handler=command_apply_adjudication)

    prepare_parser = subparsers.add_parser("prepare-protocols")
    prepare_parser.add_argument("--registry", required=True)
    prepare_parser.add_argument("--output", required=True)
    prepare_parser.add_argument("--target-characters", type=int, default=600)
    prepare_parser.add_argument("--overlap-characters", type=int, default=80)
    prepare_parser.set_defaults(handler=command_prepare_protocols)

    preprocess_queries_parser = subparsers.add_parser("preprocess-queries")
    preprocess_queries_parser.add_argument("--input", required=True)
    preprocess_queries_parser.add_argument("--output-directory", required=True)
    preprocess_queries_parser.add_argument("--seed", type=int, default=42)
    preprocess_queries_parser.add_argument("--min-characters", type=int, default=4)
    preprocess_queries_parser.add_argument(
        "--max-characters",
        type=int,
        default=1000,
    )
    preprocess_queries_parser.add_argument(
        "--augment-train-copies",
        type=int,
        choices=(0, 1, 2),
        default=0,
        help=(
            "safe punctuation-only variants; applied after group splitting "
            "to train only"
        ),
    )
    preprocess_queries_parser.add_argument(
        "--fail-on-quarantine",
        action="store_true",
    )
    preprocess_queries_parser.add_argument(
        "--preserve-existing-splits",
        action="store_true",
        help=(
            "preserve preassigned train/valid/cal_op/cal_ch/test_op/test_ch "
            "labels and fail on group leakage"
        ),
    )
    preprocess_queries_parser.set_defaults(handler=command_preprocess_queries)

    preprocess_runs_parser = subparsers.add_parser("preprocess-runs")
    preprocess_runs_parser.add_argument("--input", required=True)
    preprocess_runs_parser.add_argument("--output", required=True)
    preprocess_runs_parser.add_argument(
        "--allow-missing-energy",
        action="store_true",
        help=(
            "development only; formal resource analysis requires "
            "physical energy"
        ),
    )
    preprocess_runs_parser.add_argument(
        "--robust-z-threshold",
        type=float,
        default=3.5,
    )
    preprocess_runs_parser.add_argument(
        "--fail-on-quarantine",
        action="store_true",
    )
    preprocess_runs_parser.set_defaults(handler=command_preprocess_runs)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = int(args.handler(args))
    except BaseException:
        if getattr(args, "stop_collector_on_exit", False):
            try:
                stop_result = _send_collector_stop(args)
                print(
                    json.dumps({"collector_stop": stop_result}, ensure_ascii=False),
                    file=sys.stderr,
                )
            except Exception as stop_exc:
                print(
                    json.dumps(
                        {
                            "collector_stop": {
                                "status": "error",
                                "error_type": type(stop_exc).__name__,
                                "error": str(stop_exc),
                            }
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
        raise
    if getattr(args, "stop_collector_on_exit", False):
        try:
            stop_result = _send_collector_stop(args)
            print(
                json.dumps({"collector_stop": stop_result}, ensure_ascii=False),
                file=sys.stderr,
            )
        except Exception as stop_exc:
            print(
                json.dumps(
                    {
                        "collector_stop": {
                            "status": "error",
                            "error_type": type(stop_exc).__name__,
                            "error": str(stop_exc),
                        }
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 4 if result == 0 else result
    return result


if __name__ == "__main__":
    raise SystemExit(main())
