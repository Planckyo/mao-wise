import argparse
from pathlib import Path
import pandas as pd


def _safe_rate(series, tol: float) -> float:
    if series.isna().all() or len(series) == 0:
        return float('nan')
    return float((series.abs() <= tol).mean())


def compute_summary(tasks_with_ids: Path, results_file: Path, out_md: Path) -> None:
    tasks_df = pd.read_csv(tasks_with_ids)
    # predicted columns from tasks file
    tasks_df = tasks_df.rename(columns={"alpha": "alpha_pred", "epsilon": "epsilon_pred"})
    if results_file.exists():
        res_df = pd.read_excel(results_file)
    else:
        # create empty measured columns
        res_df = tasks_df[["experiment_id", "plan_id"]].copy()
        res_df["measured_alpha"] = pd.NA
        res_df["measured_epsilon"] = pd.NA

    df = tasks_df.merge(res_df, on=["experiment_id", "plan_id"], how="left")
    # compute errors where measured present
    has_measured = df["measured_alpha"].notna() | df["measured_epsilon"].notna()
    eval_df = df.loc[has_measured].copy()

    if eval_df.empty:
        alpha_mae = float('nan')
        eps_mae = float('nan')
        alpha_hit_003 = float('nan')
        alpha_hit_005 = float('nan')
        eps_hit_003 = float('nan')
        eps_hit_005 = float('nan')
        n_eval = 0
    else:
        eval_df["alpha_err"] = (eval_df["alpha_pred"] - eval_df["measured_alpha"]).abs()
        eval_df["eps_err"] = (eval_df["epsilon_pred"] - eval_df["measured_epsilon"]).abs()
        alpha_mae = float(eval_df["alpha_err"].mean())
        eps_mae = float(eval_df["eps_err"].mean())
        alpha_hit_003 = _safe_rate(eval_df["alpha_err"], 0.03)
        alpha_hit_005 = _safe_rate(eval_df["alpha_err"], 0.05)
        eps_hit_003 = _safe_rate(eval_df["eps_err"], 0.03)
        eps_hit_005 = _safe_rate(eval_df["eps_err"], 0.05)
        n_eval = int(len(eval_df))

    # For now, before==after (no live retrain in this minimal path)
    md = [
        "# Round-1 回传评估汇总",
        "",
        f"评估样本数: {n_eval}",
        "",
        "## 指标（前后对比）",
        "- α MAE: 前 = 后 = {0 if pd.isna(alpha_mae) else round(alpha_mae, 4)}",
        "- ε MAE: 前 = 后 = {0 if pd.isna(eps_mae) else round(eps_mae, 4)}",
        "- α 命中率 (±0.03): 前 = 后 = {0 if pd.isna(alpha_hit_003) else round(alpha_hit_003, 3)}",
        "- α 命中率 (±0.05): 前 = 后 = {0 if pd.isna(alpha_hit_005) else round(alpha_hit_005, 3)}",
        "- ε 命中率 (±0.03): 前 = 后 = {0 if pd.isna(eps_hit_003) else round(eps_hit_003, 3)}",
        "- ε 命中率 (±0.05): 前 = 后 = {0 if pd.isna(eps_hit_005) else round(eps_hit_005, 3)}",
        "",
        "备注: 当前路径未触发在线热加载，前后指标一致。若提供有效实测数据，后续可自动更新模型并生成对比。",
    ]
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks_with_ids", required=True)
    ap.add_argument("--result_file", required=True)
    ap.add_argument("--out_md", required=True)
    args = ap.parse_args()

    compute_summary(
        Path(args.tasks_with_ids), Path(args.result_file), Path(args.out_md)
    )


if __name__ == "__main__":
    main()


