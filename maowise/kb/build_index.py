from __future__ import annotations

import argparse
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
from ..utils.logger import logger


def load_corpus(jsonl_file: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with open(jsonl_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                items.append(json.loads(line))
            except Exception:
                pass
    return items


def build_index(corpus_file: str, out_dir: str) -> Dict[str, Any]:
    cfg = load_config()
    corpus_p = Path(corpus_file)
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)

    if not corpus_p.exists():
        raise FileNotFoundError(f"corpus not found: {corpus_file}")

    items = load_corpus(corpus_p)
    texts = [it.get("text", "") for it in items]
    if len(texts) == 0:
        logger.warning("empty corpus; skip index build")
        return {"ok": False, "count": 0}

    model_name = cfg["kb"].get("embed_model", "sentence-transformers/all-MiniLM-L6-v2")
    model = _get_embed_model(model_name)

    logger.info(f"embedding {len(texts)} passages with {model_name}")
    emb = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=True,
        normalize_embeddings=cfg["kb"].get("normalize_embeddings", True),
    ).astype(np.float32)

    backend = "faiss"
    try:
        import faiss  # type: ignore

        dim = emb.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(emb)
        faiss.write_index(index, str(out_dir_p / "faiss.index"))
        logger.info("faiss index written")
    except Exception:
        backend = "numpy"
        np.save(out_dir_p / "embeddings.npy", emb)
        logger.warning("faiss not available; saved embeddings.npy for numpy backend")

    with open(out_dir_p / "passages.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    with open(out_dir_p / "meta.json", "w", encoding="utf-8") as f:
        json.dump({"backend": backend, "model": model_name}, f)

    logger.info(f"index built ({backend}): {out_dir_p}")
    return {"ok": True, "count": len(items), "backend": backend}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True, type=str)
    parser.add_argument("--out_dir", required=True, type=str)
    args = parser.parse_args()
    build_index(args.corpus, args.out_dir)

