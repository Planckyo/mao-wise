from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List
import numpy as np
from joblib import load

from ..utils import load_config
from ..utils.logger import logger
from .dataset_builder import parse_free_text_to_slots, compose_input_text_from_slots
from ..kb.search import kb_search


class _ConstantModel:
    def predict(self, X):
        import numpy as _np
        return _np.tile(_np.array([[0.5, 0.5]], dtype=float), (len(X), 1))


class ForwardModel:
    def __init__(self) -> None:
        cfg = load_config()
        ckpt_dir = Path(cfg["fwd_model"]["checkpoint_dir"])
        model_file = ckpt_dir / "model.joblib"
        self.ok = False
        if model_file.exists():
            bundle = load(model_file)
            self.model = bundle["model"]
            self.embed_model_name = bundle.get("embed_model", "sentence-transformers/all-MiniLM-L6-v2")
            self.embed = _get_embed_model(self.embed_model_name)
            self.ok = True
        else:
            logger.warning(f"forward model not found: {model_file}")
            self.embed = _get_embed_model("sentence-transformers/all-MiniLM-L6-v2")
            self.model = _ConstantModel()

    def predict(self, description: str) -> Dict[str, Any]:
        slots = parse_free_text_to_slots(description)
        text = compose_input_text_from_slots(slots)
        X = self.embed.encode([text], convert_to_numpy=True, normalize_embeddings=True)
        y = self.model.predict(X)
        alpha, epsilon = float(y[0][0]), float(y[0][1])
        # 置信度：基于相似案例得分（0-1 归一）
        try:
            cases = kb_search(description, k=3)
        except Exception:
            cases = []
        if cases:
            scores = np.array([c["score"] for c in cases], dtype=float)
            s = float(scores.mean())
            # FAISS 内积相似度，近似在 [0,1]
            confidence = float(np.clip((s + 1) / 2.0, 0, 1))
        else:
            confidence = 0.5
        return {
            "alpha": float(np.clip(alpha, 0, 1)),
            "epsilon": float(np.clip(epsilon, 0, 1)),
            "confidence": confidence,
            "nearest_cases": cases,
        }


_MODEL: ForwardModel | None = None


def get_model() -> ForwardModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = ForwardModel()
    return _MODEL


def predict_performance(description: str, topk_cases: int = 3) -> Dict[str, Any]:
    """
    returns: {"alpha": float, "epsilon": float, "confidence": float, "nearest_cases":[...]}
    """
    m = get_model()
    out = m.predict(description)
    out["nearest_cases"] = out.get("nearest_cases", [])[:topk_cases]
    return out


def _get_embed_model(model_name: str):
    """安全获取嵌入模型，离线或报错时退化为 DummyEmbed。"""
    try:
        from sentence_transformers import SentenceTransformer  # lazy import

        return SentenceTransformer(model_name)
    except Exception:
        class DummyEmbed:
            def encode(self, texts, convert_to_numpy=True, normalize_embeddings=True):
                import numpy as _np
                if isinstance(texts, str):
                    texts = [texts]
                # 简单 hash 维度 64
                dim = 64
                emb = _np.zeros((len(texts), dim), dtype=_np.float32)
                for i, t in enumerate(texts):
                    h = abs(hash(t))
                    _np.random.seed(h % (2**32 - 1))
                    emb[i] = _np.random.rand(dim)
                if normalize_embeddings:
                    n = _np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9
                    emb = emb / n
                return emb
        logger.warning("SentenceTransformer 加载失败，使用 DummyEmbed")
        return DummyEmbed()

