from __future__ import annotations

from typing import List, Dict, Any
from pathlib import Path
import fitz  # PyMuPDF
from ..utils.logger import logger


def extract_pdf_to_corpus(pdf_path: str | Path) -> List[Dict[str, Any]]:
    """
    将 PDF 每页文本抽取为段落块（简单版本：整页作为一个块）。
    返回列表，每项包含: {doc_id, page, text, span_bbox}
    """
    pdf_path = Path(pdf_path)
    doc_id = pdf_path.stem
    corpus: List[Dict[str, Any]] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error(f"open pdf failed: {pdf_path} {e}")
        return corpus

    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        # span_bbox 暂无，保留 None
        corpus.append({
            "doc_id": doc_id,
            "page": i + 1,
            "text": text,
            "span_bbox": None,
            "source_pdf": str(pdf_path)
        })

    doc.close()
    logger.info(f"extracted pages: {pdf_path} -> {len(corpus)}")
    return corpus

