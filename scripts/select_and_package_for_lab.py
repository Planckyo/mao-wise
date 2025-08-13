import argparse
import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import pandas as pd


@dataclass
class SelectionParams:
    alpha_max: float
    epsilon_min: float
    conf_min: float
    mass_max: float
    uniform_max: float
    k_explore: int
    n_top: int


def _load_plans(plans_path: Path) -> pd.DataFrame:
    if not plans_path.exists():
        raise FileNotFoundError(f"plans.csv not found: {plans_path}")
    df = pd.read_csv(plans_path)
    # Normalize expected columns
    expected_cols = [
        "plan_id",
        "batch_id",
        "system",
        "alpha",
        "epsilon",
        "confidence",
        "hard_constraints_passed",
        "mass_proxy",
        "uniformity_penalty",
        "score_total",
    ]
    for c in expected_cols:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in {plans_path}")
    return df


def _select_conservative(
    df: pd.DataFrame, p: SelectionParams
) -> Tuple[pd.DataFrame, bool]:
    """Select conservative set; relax confidence to 0.50 if needed."""
    base = df.copy()
    # Ensure numeric types
    for col in ["alpha", "epsilon", "confidence", "mass_proxy", "uniformity_penalty", "score_total"]:
        base[col] = pd.to_numeric(base[col], errors="coerce")
    # Boolean pass
    if "hard_constraints_passed" in base.columns:
        mask_hard = base["hard_constraints_passed"].astype(str).str.lower().isin(["true", "1", "yes"]) | (base["hard_constraints_passed"] == True)
    else:
        mask_hard = True

    def run_filter(conf_min: float) -> pd.DataFrame:
        mask = (
            (base["alpha"] <= p.alpha_max)
            & (base["epsilon"] >= p.epsilon_min)
            & (base["confidence"] >= conf_min)
            & (base["mass_proxy"] <= p.mass_max)
            & (base["uniformity_penalty"] <= p.uniform_max)
            & (mask_hard)
        )
        sub = base.loc[mask].sort_values(["score_total", "confidence", "epsilon"], ascending=[False, False, False])
        return sub.head(p.n_top)

    conservative = run_filter(p.conf_min)
    relaxed_used = False
    if len(conservative) < p.n_top:
        # Relax confidence to 0.50
        conservative = run_filter(0.50)
        relaxed_used = True
    return conservative, relaxed_used


def _select_explore(df: pd.DataFrame, exclude_ids: List[str], k: int) -> pd.DataFrame:
    pool = df[~df["plan_id"].isin(exclude_ids)].copy()
    for col in ["score_total", "confidence", "epsilon"]:
        pool[col] = pd.to_numeric(pool[col], errors="coerce")
    # Prefer high score_total as exploration candidates
    pool = pool.sort_values(["score_total", "confidence", "epsilon"], ascending=[False, False, False])
    return pool.head(k)


def _copy_yaml_for_plans(plans_dir: Path, plans: pd.DataFrame, out_yaml_dir: Path) -> int:
    out_yaml_dir.mkdir(parents=True, exist_ok=True)
    yaml_dir = plans_dir / "plans_yaml"
    copied = 0
    for plan_id in plans["plan_id"].tolist():
        src = yaml_dir / f"{plan_id}.yaml"
        if src.exists():
            dst = out_yaml_dir / src.name
            shutil.copy2(src, dst)
            copied += 1
    return copied


def select_and_package(plans_csv: Path, outdir: Path, params: SelectionParams) -> Tuple[pd.DataFrame, bool, int, int, int]:
    df = _load_plans(plans_csv)
    conservative, relaxed_used = _select_conservative(df, params)
    explore = _select_explore(df, exclude_ids=conservative["plan_id"].tolist(), k=params.k_explore)

    conservative = conservative.copy()
    conservative["set"] = "conservative"
    explore = explore.copy()
    explore["set"] = "explore"

    selected = pd.concat([conservative, explore], ignore_index=True)

    outdir.mkdir(parents=True, exist_ok=True)
    # Save exp_tasks.csv
    cols = [
        "plan_id",
        "batch_id",
        "system",
        "alpha",
        "epsilon",
        "confidence",
        "mass_proxy",
        "uniformity_penalty",
        "score_total",
        "set",
    ]
    selected.to_csv(outdir / "exp_tasks.csv", index=False, columns=cols)

    # Copy YAMLs
    copied_yaml = _copy_yaml_for_plans(plans_csv.parent, selected, outdir / "plans_yaml")

    return selected, relaxed_used, len(conservative), len(explore), copied_yaml


def main() -> None:
    ap = argparse.ArgumentParser(description="Select and package R1 lab experiments")
    ap.add_argument("--plans", required=True, help="Path to latest batch plans.csv")
    ap.add_argument("--alpha_max", type=float, required=True)
    ap.add_argument("--epsilon_min", type=float, required=True)
    ap.add_argument("--conf_min", type=float, required=True)
    ap.add_argument("--mass_max", type=float, required=True)
    ap.add_argument("--uniform_max", type=float, required=True)
    ap.add_argument("--k_explore", type=int, required=True)
    ap.add_argument("--n_top", type=int, required=True)
    ap.add_argument("--outdir", type=str, required=True)
    args = ap.parse_args()

    plans_csv = Path(args.plans).resolve()
    outdir = Path(args.outdir).resolve()
    params = SelectionParams(
        alpha_max=args.alpha_max,
        epsilon_min=args.epsilon_min,
        conf_min=args.conf_min,
        mass_max=args.mass_max,
        uniform_max=args.uniform_max,
        k_explore=args.k_explore,
        n_top=args.n_top,
    )

    selected, relaxed_used, n_cons, n_explore, copied_yaml = select_and_package(plans_csv, outdir, params)

    # Print summary to stdout
    print("\n==== R1 实验包筛选结果 ====")
    print(f"保守集数: {n_cons}")
    print(f"探索集数: {n_explore}")
    print(f"总入选数: {len(selected)}")
    print(f"YAML文件复制数: {copied_yaml}")
    print(f"是否触发放宽到 conf_min=0.50: {'是' if relaxed_used else '否'}")
    print(f"输出目录: {outdir}")


if __name__ == "__main__":
    main()


