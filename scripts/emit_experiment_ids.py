import argparse
import datetime as dt
from pathlib import Path
import pandas as pd


def mask(s: str, keep: int = 4) -> str:
    if not s:
        return s
    return s[:keep] + "***"


def main() -> None:
    ap = argparse.ArgumentParser(description="Emit experiment IDs and result template")
    ap.add_argument("--tasks", required=True, help="Path to lab_package_R1/exp_tasks.csv")
    args = ap.parse_args()

    tasks_path = Path(args.tasks).resolve()
    if not tasks_path.exists():
        raise FileNotFoundError(f"Tasks file not found: {tasks_path}")

    df = pd.read_csv(tasks_path)
    today = dt.datetime.now().strftime("%Y%m%d")
    # Generate experiment_id: R1-YYYYMMDD-XXXX
    df = df.reset_index(drop=True)
    df["experiment_id"] = [f"R1-{today}-{i+1:04d}" for i in range(len(df))]

    out_with_ids = tasks_path.parent / "exp_tasks_with_ids.csv"
    cols = ["experiment_id"] + [c for c in df.columns if c != "experiment_id"]
    df.to_csv(out_with_ids, index=False, columns=cols)

    # Emit results template
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    template_path = results_dir / "round1_results_template.xlsx"

    tpl_cols = [
        "experiment_id",
        "plan_id",
        "batch_id",
        "system",
        "alpha_pred",
        "epsilon_pred",
        "confidence",
        "mass_proxy",
        "uniformity_penalty",
        "measured_alpha",
        "measured_epsilon",
        "notes",
    ]
    tpl = pd.DataFrame(
        {
            "experiment_id": df["experiment_id"],
            "plan_id": df.get("plan_id"),
            "batch_id": df.get("batch_id"),
            "system": df.get("system"),
            "alpha_pred": df.get("alpha"),
            "epsilon_pred": df.get("epsilon"),
            "confidence": df.get("confidence"),
            "mass_proxy": df.get("mass_proxy"),
            "uniformity_penalty": df.get("uniformity_penalty"),
            "measured_alpha": None,
            "measured_epsilon": None,
            "notes": None,
        }
    )
    tpl.to_excel(template_path, index=False)

    print("发放实验编号完成")
    print(f"任务文件: {tasks_path}")
    print(f"带编号文件: {out_with_ids}")
    print(f"结果模板: {template_path}")


if __name__ == "__main__":
    main()


