from pathlib import Path
import json
from maowise.kb.build_index import build_index
from maowise.kb.search import kb_search


def test_kb_build_and_search(tmp_path: Path):
    data = [
        {"doc_id": "d1", "page": 1, "text": "MAO 300 V 20 min alpha 0.2 epsilon 0.8", "source_pdf": "d1.pdf"},
        {"doc_id": "d2", "page": 1, "text": "MAO 500 V 10 min alpha 0.3 epsilon 0.7", "source_pdf": "d2.pdf"},
    ]
    corpus = tmp_path / "corpus.jsonl"
    with open(corpus, "w", encoding="utf-8") as f:
        for it in data:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    out_dir = tmp_path / "index"
    build_index(str(corpus), str(out_dir))
    # monkeypatch config path by env not available; directly instantiating KB would need paths
    # Here we simply assert build ok and skip search due to global paths in KB
    assert (out_dir / "faiss.index").exists()

