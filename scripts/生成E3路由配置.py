from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="从基础Radxa配置生成E3/E4三种能耗路由配置")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--model-directory", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    base = json.loads(args.base.read_text(encoding="utf-8"))
    local_project_root = args.base.resolve().parents[1]
    args.output_directory.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for mode in ("soft_weighting", "static_mean", "no_state", "state_aware"):
        config = json.loads(json.dumps(base))
        router = config.setdefault("router", {})
        router["energy_budget_env"] = "SCI_EXP_ENERGY_BUDGET_J"
        router["memory_headroom_fraction"] = 0.9
        if mode in {"soft_weighting", "static_mean"}:
            router.pop("energy_model_file", None)
        else:
            model_path = args.model_directory / f"energy_{mode}.joblib"
            resolved_model = (
                model_path.resolve()
                if model_path.is_absolute()
                else (Path.cwd() / model_path).resolve()
            )
            try:
                relative = resolved_model.relative_to(local_project_root)
                router["energy_model_file"] = str(relative).replace("\\", "/")
            except ValueError:
                raise SystemExit(
                    f"能耗模型必须位于工程目录内，当前路径: {resolved_model}"
                )
        config.setdefault("experiment", {})["policy_name"] = f"safety_router_{mode}"
        if mode == "soft_weighting":
            router["policy"] = "soft_weighting"
            router["soft_risk_weight"] = 0.8
            config["experiment"]["policy_name"] = "soft_weighting"
        else:
            router["policy"] = "hard_safety"
        path = args.output_directory / f"radxa.e4.{mode}.json"
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        outputs[mode] = str(path)
    print(json.dumps(outputs, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
