from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
import hashlib
import pandas as pd

from ..utils import load_config
from ..utils.logger import logger
from .extract_pdf import extract_pdf_to_corpus
from .ner_rules import extract_fields_from_text
from .normalize import normalize_record_values
from ..utils.schema import validate_record


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def process_pdf(pdf_path: Path) -> Dict[str, Any]:
    corpus = extract_pdf_to_corpus(pdf_path)
    samples: List[Dict[str, Any]] = []

    # Naive: 每页作为一个块；若块内同时有 α 和 ε 则形成一个样本
    # 其余字段由规则抽取填充
    for block in corpus:
        fields = extract_fields_from_text(block.get("text", ""))
        if "alpha_150_2600" in fields and "epsilon_3000_30000" in fields:
            rec: Dict[str, Any] = {
                "substrate_alloy": "<unk>",
                "electrolyte_family": fields.get("electrolyte_family", "mixed"),
                "electrolyte_components": [],
                "mode": fields.get("mode", "dc"),
                "voltage_V": fields.get("voltage_V", 300.0),
                "current_density_A_dm2": fields.get("current_density_A_dm2", 10.0),
                "frequency_Hz": fields.get("frequency_Hz", 1000.0),
                "duty_cycle_pct": fields.get("duty_cycle_pct", 30.0),
                "time_min": fields.get("time_min", 20.0),
                "temp_C": fields.get("temp_C"),
                "pH": fields.get("pH"),
                "sealing": "none",
                "thickness_um": None,
                "roughness_Ra_um": None,
                "porosity_pct": None,
                "phases": [],
                "alpha_150_2600": fields["alpha_150_2600"],
                "epsilon_3000_30000": fields["epsilon_3000_30000"],
                "source_pdf": str(pdf_path),
                "page": block["page"],
                "span_bbox": block.get("span_bbox"),
                "citation": None,
                "sample_id": f"{pdf_path.stem}-{block['page']}",
                "extraction_status": "ok",
            }
            rec = normalize_record_values(rec)
            rec = validate_record(rec)
            samples.append(rec)

    return {"corpus": corpus, "samples": samples}


def write_outputs(out_dir: Path, pdf_to_result: Dict[str, Any], corpus_all: List[Dict[str, Any]]) -> Dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    versions_dir = out_dir
    parsed_dir = Path(load_config()["paths"]["data_parsed"])  # datasets/data_parsed
    parsed_dir.mkdir(parents=True, exist_ok=True)

    # samples parquet
    all_samples: List[Dict[str, Any]] = []
    for r in pdf_to_result.values():
        all_samples.extend(r["samples"])
    df = pd.DataFrame(all_samples)
    samples_file = versions_dir / "samples.parquet"
    if not df.empty:
        df.to_parquet(samples_file, index=False)
    else:
        # create empty DataFrame with columns
        df = pd.DataFrame(columns=["sample_id"])  # minimal
        df.to_parquet(samples_file, index=False)

    # corpus jsonl
    corpus_file = parsed_dir / "corpus.jsonl"
    with open(corpus_file, "w", encoding="utf-8") as f:
        for blk in corpus_all:
            f.write(json.dumps(blk, ensure_ascii=False) + "\n")

    # provenance sqlite
    prov_file = versions_dir / "provenance.sqlite"
    conn = sqlite3.connect(prov_file)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS provenance (doc_id TEXT PRIMARY KEY, pdf_path TEXT, sha256 TEXT)")
    for doc_id, r in pdf_to_result.items():
        pdf_path = r["pdf_path"]
        sha = _hash_file(Path(pdf_path)) if Path(pdf_path).exists() else ""
        cur.execute("INSERT OR REPLACE INTO provenance (doc_id, pdf_path, sha256) VALUES (?,?,?)", (doc_id, pdf_path, sha))
    conn.commit()
    conn.close()

    return {"samples": len(all_samples), "parsed": len(corpus_all)}


def main(pdf_dir: str, out_dir: str) -> Dict[str, int]:
    pdf_dir_p = Path(pdf_dir)
    out_dir_p = Path(out_dir)
    pdf_files = sorted([p for p in pdf_dir_p.glob("*.pdf")])
    logger.info(f"ingest PDFs: {len(pdf_files)} from {pdf_dir}")
    pdf_to_result: Dict[str, Any] = {}
    corpus_all: List[Dict[str, Any]] = []

    for pdf in pdf_files:
        res = process_pdf(pdf)
        corpus_all.extend(res["corpus"])        
        pdf_to_result[pdf.stem] = {"pdf_path": str(pdf), **res}

    stats = write_outputs(out_dir_p, pdf_to_result, corpus_all)
    logger.info(f"ingest done: samples={stats['samples']} parsed_blocks={stats['parsed']}")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf_dir", required=True, type=str)
    parser.add_argument("--out_dir", required=True, type=str)
    args = parser.parse_args()
    main(args.pdf_dir, args.out_dir)

