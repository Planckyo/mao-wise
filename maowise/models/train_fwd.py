from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import numpy as np
from joblib import dump
from sklearn.linear_model import Ridge
from sklearn.multioutput import MultiOutputRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel
from sklearn.neighbors import KNeighborsRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split
from sentence_transformers import SentenceTransformer
import mlflow

from ..utils import load_config
from ..utils.logger import logger
from .dataset_builder import render_training_text


def _embed_texts(texts: list[str], model_name: str) -> np.ndarray:
    try:
        model = SentenceTransformer(model_name)
    except Exception:
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    emb = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return emb


def _fit_gp_corrector(X_train, epsilon_residuals, system: str, min_samples_gp: int = 10):
    """拟合高斯过程残差校正器，小样本时回退到KNN"""
    if len(X_train) < min_samples_gp:
        logger.info(f"样本数({len(X_train)}) < {min_samples_gp}，使用KNN替代GP for {system}")
        corrector = KNeighborsRegressor(n_neighbors=min(3, len(X_train)), weights='distance')
    else:
        # 高斯过程回归器，RBF+WhiteKernel
        kernel = RBF(length_scale=1.0, length_scale_bounds=(1e-2, 1e2)) + WhiteKernel(noise_level=1e-5, noise_level_bounds=(1e-10, 1e+1))
        corrector = GaussianProcessRegressor(kernel=kernel, alpha=1e-6, n_restarts_optimizer=5)
    
    corrector.fit(X_train, epsilon_residuals)
    return corrector


def _fit_isotonic_calibrator(epsilon_true, epsilon_corrected):
    """拟合等温回归校准器"""
    calibrator = IsotonicRegression(out_of_bounds='clip')
    calibrator.fit(epsilon_corrected, epsilon_true)
    return calibrator


def train(samples_file: str, out_dir: str, model_name: str = "BAAI/bge-m3") -> Dict[str, Any]:
    df = pd.read_parquet(samples_file)
    if df.empty:
        raise RuntimeError("empty samples for training")
    
    # 检查是否有system列进行分体系训练
    has_system = 'system' in df.columns
    systems = df['system'].unique() if has_system else ['default']
    
    logger.info(f"开始训练，体系: {systems}")
    
    texts = [render_training_text(r) for r in df.fillna("").to_dict(orient="records")]
    X = _embed_texts(texts, model_name)
    y = df[["measured_alpha", "measured_epsilon"]].values.astype(float)

    # 主回归模型训练
    model = MultiOutputRegressor(Ridge(alpha=1.0))
    model.fit(X, y)
    y_pred = model.predict(X)

    # 基础指标
    base_metrics = {
        "mae_alpha": float(mean_absolute_error(y[:, 0], y_pred[:, 0])),
        "mae_epsilon": float(mean_absolute_error(y[:, 1], y_pred[:, 1])),
        "rmse_alpha": float(np.sqrt(mean_squared_error(y[:, 0], y_pred[:, 0]))),
        "rmse_epsilon": float(np.sqrt(mean_squared_error(y[:, 1], y_pred[:, 1]))),
        "r2_alpha": float(r2_score(y[:, 0], y_pred[:, 0])),
        "r2_epsilon": float(r2_score(y[:, 1], y_pred[:, 1])),
    }
    
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    
    # 分体系训练epsilon残差校正器
    corrector_metrics = {}
    
    for system in systems:
        if has_system:
            system_mask = df['system'] == system
            X_sys = X[system_mask]
            y_sys = y[system_mask]
            y_pred_sys = y_pred[system_mask]
        else:
            X_sys = X
            y_sys = y
            y_pred_sys = y_pred
            
        if len(X_sys) < 3:
            logger.warning(f"体系 {system} 样本数过少({len(X_sys)})，跳过校正器训练")
            continue
        
        # 计算epsilon残差
        epsilon_residuals = y_sys[:, 1] - y_pred_sys[:, 1]  # true - pred
        
        # 训练GP校正器
        try:
            gp_corrector = _fit_gp_corrector(X_sys, epsilon_residuals, system)
            gp_file = out_dir_p / f"gp_epsilon_{system}.pkl"
            dump(gp_corrector, gp_file)
            logger.info(f"GP校正器已保存: {gp_file}")
            
            # 获取校正后的epsilon预测
            epsilon_corrections = gp_corrector.predict(X_sys)
            epsilon_corrected = y_pred_sys[:, 1] + epsilon_corrections
            
            # 训练等温回归校准器
            isotonic_calibrator = _fit_isotonic_calibrator(y_sys[:, 1], epsilon_corrected)
            calib_file = out_dir_p / f"calib_epsilon_{system}.pkl"
            dump(isotonic_calibrator, calib_file)
            logger.info(f"等温校准器已保存: {calib_file}")
            
            # 最终校正后的预测
            epsilon_final = isotonic_calibrator.predict(epsilon_corrected)
            
            # 校正器性能评估
            mae_before = float(mean_absolute_error(y_sys[:, 1], y_pred_sys[:, 1]))
            mae_after_gp = float(mean_absolute_error(y_sys[:, 1], epsilon_corrected))
            mae_after_calib = float(mean_absolute_error(y_sys[:, 1], epsilon_final))
            
            corrector_metrics[system] = {
                "samples": len(X_sys),
                "epsilon_mae_before": mae_before,
                "epsilon_mae_after_gp": mae_after_gp,
                "epsilon_mae_after_calib": mae_after_calib,
                "improvement_gp": mae_before - mae_after_gp,
                "improvement_total": mae_before - mae_after_calib,
                "corrector_type": "GP" if len(X_sys) >= 10 else "KNN"
            }
            
        except Exception as e:
            logger.error(f"训练体系 {system} 校正器失败: {e}")
            corrector_metrics[system] = {"error": str(e)}
    
    # 合并所有指标
    metrics = {
        **base_metrics,
        "corrector_metrics": corrector_metrics,
        "systems_trained": list(systems),
        "total_samples": len(df)
    }

    # 保存主模型
    dump({"model": model, "embed_model": model_name}, out_dir_p / "model.joblib")

    cfg = load_config()
    Path(cfg["paths"]["reports"]).mkdir(parents=True, exist_ok=True)
    report_file = Path(cfg["paths"]["reports"]) / "fwd_eval_v1.json"
    import json
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    try:
        mlflow.set_tracking_uri(Path("mlruns").absolute().as_uri())
        with mlflow.start_run(run_name="train_fwd_v1"):
            for k, v in metrics.items():
                mlflow.log_metric(k, v)
            mlflow.log_param("embed_model", model_name)
            mlflow.log_artifact(str(report_file))
    except Exception:
        logger.warning("mlflow logging skipped")

    logger.info(f"training done, metrics: {metrics}")
    return {"ok": True, **metrics}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True, type=str)
    parser.add_argument("--model_name", required=False, type=str, default="BAAI/bge-m3")
    parser.add_argument("--out_dir", required=True, type=str)
    parser.add_argument("--epochs", required=False, type=int, default=8)  # 占位
    parser.add_argument("--lr", required=False, type=float, default=2e-5)  # 占位
    parser.add_argument("--batch", required=False, type=int, default=16)  # 占位
    args = parser.parse_args()
    train(args.samples, args.out_dir, model_name=args.model_name)

