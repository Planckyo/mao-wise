from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
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


def process_pdf(pdf_path: Path, split_name: Optional[str] = None, file_md5: Optional[str] = None, use_ocr: bool = False, use_llm_slotfill: bool = False) -> Dict[str, Any]:
    corpus = extract_pdf_to_corpus(pdf_path)
    samples: List[Dict[str, Any]] = []

    # Naive: 每页作为一个块；若块内同时有 α 和 ε 则形成一个样本
    # 其余字段由规则抽取填充，可选LLM SlotFill增强
    for block in corpus:
        # 1. 先用规则抽取
        fields = extract_fields_from_text(block.get("text", ""))
        extractor_method = "rules"
        
        # 2. 如果启用LLM SlotFill且规则抽取有缺失槽位，则用LLM补充
        if use_llm_slotfill and ("alpha_150_2600" in fields and "epsilon_3000_30000" in fields):
            try:
                from ..experts.slotfill import extract_slot_values
                # 检查哪些槽位缺失或为默认值
                missing_slots = []
                if fields.get("substrate_alloy", "<unk>") == "<unk>":
                    missing_slots.append("substrate_alloy")
                if fields.get("electrolyte_family", "mixed") == "mixed":
                    missing_slots.append("electrolyte_family")
                if not fields.get("electrolyte_components"):
                    missing_slots.append("electrolyte_components")
                
                if missing_slots:
                    llm_fields = extract_slot_values(block.get("text", ""), missing_slots)
                    if llm_fields:
                        # 合并LLM结果，LLM结果优先级更高
                        fields.update(llm_fields)
                        extractor_method = "rules+llm"
            except Exception as e:
                logger.warning(f"LLM SlotFill failed for {pdf_path} page {block.get('page', '?')}: {e}")
        
        if "alpha_150_2600" in fields and "epsilon_3000_30000" in fields:
            rec: Dict[str, Any] = {
                "substrate_alloy": fields.get("substrate_alloy", "<unk>"),
                "electrolyte_family": fields.get("electrolyte_family", "mixed"),
                "electrolyte_components": fields.get("electrolyte_components", []),
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
                "extractor": extractor_method,  # 新增：标记抽取方法
                "split": split_name,
                "md5": file_md5,
                "doi": None,
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
        # 去重：按 source_pdf+page+span_bbox 哈希
        def _rec_key(row):
            bb = row.get("span_bbox")
            return f"{row.get('source_pdf','')}|{row.get('page','')}|{bb}"
        df["_rec_key"] = df.apply(_rec_key, axis=1)
        if samples_file.exists():
            try:
                old = pd.read_parquet(samples_file)
                if "_rec_key" not in old.columns:
                    def _old_key(row):
                        bb = row.get("span_bbox") if isinstance(row, dict) else row["span_bbox"] if "span_bbox" in row else None
                        return f"{row.get('source_pdf','')}|{row.get('page','')}|{bb}" if isinstance(row, dict) else f"{row['source_pdf']}|{row['page']}|{bb}"
                    old["_rec_key"] = old.apply(_old_key, axis=1)
                df = pd.concat([old, df], ignore_index=True)
            except Exception:
                pass
        df = df.drop_duplicates(subset=["_rec_key"])\
               .drop(columns=["_rec_key"])\
               .reset_index(drop=True)
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


def main(pdf_dir: Optional[str], out_dir: str, manifest: Optional[str] = None, split_name: Optional[str] = None, use_ocr: bool = False, use_llm_slotfill: bool = False) -> Dict[str, int]:
    out_dir_p = Path(out_dir)
    if manifest:
        import csv
        pdf_files = []
        with open(manifest, "r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                pdf_files.append({"path": Path(r["pdf_path"]).resolve(), "md5": r.get("md5")})
        logger.info(f"ingest manifest rows: {len(pdf_files)} from {manifest}")
    else:
        assert pdf_dir is not None, "pdf_dir required when manifest not provided"
        pdf_dir_p = Path(pdf_dir)
        pdf_files = [{"path": p, "md5": None} for p in sorted([p for p in pdf_dir_p.glob("*.pdf")])]
        logger.info(f"ingest PDFs: {len(pdf_files)} from {pdf_dir}")
    pdf_to_result: Dict[str, Any] = {}
    corpus_all: List[Dict[str, Any]] = []

    for item in pdf_files:
        pdf = item["path"]
        md5 = item.get("md5")
        res = process_pdf(pdf, split_name=split_name, file_md5=md5, use_ocr=use_ocr, use_llm_slotfill=use_llm_slotfill)
        corpus_all.extend(res["corpus"])        
        pdf_to_result[pdf.stem] = {"pdf_path": str(pdf), **res}

    stats = write_outputs(out_dir_p, pdf_to_result, corpus_all)
    logger.info(f"ingest done: samples={stats['samples']} parsed_blocks={stats['parsed']}")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf_dir", required=False, type=str)
    parser.add_argument("--out_dir", required=True, type=str)
    parser.add_argument("--manifest", required=False, type=str)
    parser.add_argument("--split_name", required=False, type=str, choices=["train", "val", "test"])
    parser.add_argument("--use_ocr", required=False, type=str, default="false")
    parser.add_argument("--use_llm_slotfill", required=False, type=str, default="false")
    args = parser.parse_args()
    use_ocr = str(args.use_ocr).lower() in ("1", "true", "yes")
    use_llm_slotfill = str(args.use_llm_slotfill).lower() in ("1", "true", "yes")
    main(args.pdf_dir, args.out_dir, manifest=args.manifest, split_name=args.split_name, use_ocr=use_ocr, use_llm_slotfill=use_llm_slotfill)

