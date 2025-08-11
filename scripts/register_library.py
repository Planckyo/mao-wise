import argparse, hashlib, csv, re, sys
from pathlib import Path
import fitz  # PyMuPDF


def md5sum(p: Path, block: int = 8192) -> str:
    h = hashlib.md5()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(block), b''):
            h.update(chunk)
    return h.hexdigest()


def guess_year_from_name(name: str):
    m = re.search(r'(20\d{2}|19\d{2})', name)
    return int(m.group(1)) if m else None


def read_meta(pdf_path: Path):
    try:
        with fitz.open(pdf_path) as doc:
            info = doc.metadata or {}
            title = (info.get("title") or "").strip() or None
            doi = None
            for k in ("title", "keywords", "subject"):
                v = info.get(k) or ""
                m = re.search(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', v, re.I)
                if m:
                    doi = m.group(0)
                    break
            return title, doi
    except Exception:
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf_dir", required=True)
    ap.add_argument("--out", default="manifests/library_manifest.csv")
    args = ap.parse_args()

    pdf_root = Path(args.pdf_dir).expanduser().resolve()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for p in pdf_root.rglob("*.pdf"):
        try:
            path = p.resolve()
            md5 = md5sum(path)
            size = path.stat().st_size
            yname = guess_year_from_name(path.name)
            title, doi = read_meta(path)
            lang = "zh" if re.search(r'[\u4e00-\u9fff]', path.name) else "en"
            rows.append({
                "pdf_path": str(path),
                "md5": md5,
                "filesize": size,
                "guess_year": yname,
                "lang": lang,
                "doi": doi,
                "title": title
            })
        except Exception as e:
            print(f"[WARN] skip {p}: {e}", file=sys.stderr)

    seen_doi, seen_md5 = set(), set()
    dedup = []
    for r in rows:
        doi, md5 = r["doi"], r["md5"]
        if doi:
            if doi in seen_doi:
                continue
            seen_doi.add(doi)
        else:
            if md5 in seen_md5:
                continue
            seen_md5.add(md5)
        dedup.append(r)

    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pdf_path","md5","filesize","guess_year","lang","doi","title"])
        w.writeheader()
        for r in dedup:
            w.writerow(r)

    print(f"[OK] manifest -> {out} (rows={len(dedup)})")


if __name__ == "__main__":
    main()

