from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any

import numpy as np
def _get_embed_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer  # lazy
        return SentenceTransformer(model_name)
    except Exception:
        from maowise.models.infer_fwd import _get_embed_model as _fallback
        return _fallback(model_name)

from ..utils import load_config


class KB:
    def __init__(self, index_dir: str | Path | None = None) -> None:
        cfg = load_config()
        self.index_dir = Path(index_dir or cfg["paths"]["index_store"])
        self.passages: List[Dict[str, Any]] = []
        self.index = None
        self.backend = "none"
        try:
            import faiss  # type: ignore

            self.index = faiss.read_index(str(self.index_dir / "faiss.index"))
            self.backend = "faiss"
        except Exception:
            self.index = None
        try:
            with open(self.index_dir / "passages.jsonl", "r", encoding="utf-8") as f:
                for line in f:
                    self.passages.append(json.loads(line))
        except Exception:
            self.passages = []
        # numpy backend fallback
        self.emb = None
        if self.index is None:
            try:
                self.emb = np.load(self.index_dir / "embeddings.npy")
                self.backend = "numpy"
            except Exception:
                self.emb = None
        model_name = cfg["kb"].get("embed_model", "sentence-transformers/all-MiniLM-L6-v2")
        self.model = _get_embed_model(model_name)
        self.normalize = cfg["kb"].get("normalize_embeddings", True)

    def search(self, query: str, k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        if len(self.passages) == 0:
            return []
        q = self.model.encode([query], convert_to_numpy=True, normalize_embeddings=self.normalize).astype(np.float32)
        results: List[Dict[str, Any]] = []
        if self.backend == "faiss" and self.index is not None:
            import faiss  # type: ignore

            D, I = self.index.search(q, k)
            pairs = list(zip(D[0], I[0]))
        elif self.backend == "numpy" and self.emb is not None:
            # inner product search
            D = (q @ self.emb.T)[0]
            I = np.argsort(-D)[:k]
            pairs = [(float(D[i]), int(i)) for i in I]
        else:
            return []

        for score, idx in pairs:
            if idx < 0 or idx >= len(self.passages):
                continue
            p = self.passages[idx]
            url = f"file://{p.get('source_pdf', p.get('doc_id',''))}#page={p.get('page',1)}"
            results.append({
                "doc_id": p.get("doc_id", ""),
                "page": p.get("page", 1),
                "score": float(score),
                "snippet": p.get("text", "")[:500],
                "citation_url": url,
            })
        return results


def kb_search(query: str, k: int = 5, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    kb = KB()
    return kb.search(query, k=k, filters=filters)

