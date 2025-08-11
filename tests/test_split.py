from pathlib import Path
import csv
import subprocess


def test_make_split_and_check(tmp_path: Path):
    # prepare tiny manifest
    out_dir = tmp_path / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "library_manifest.csv"
    rows = [
        {"pdf_path": str(tmp_path / "a.pdf"), "md5": "m1", "filesize": 1, "guess_year": 2019, "lang": "en", "doi": "d1", "title": "t1"},
        {"pdf_path": str(tmp_path / "b.pdf"), "md5": "m2", "filesize": 1, "guess_year": 2012, "lang": "en", "doi": "d2", "title": "t2"},
        {"pdf_path": str(tmp_path / "c.pdf"), "md5": "m3", "filesize": 1, "guess_year": 2022, "lang": "en", "doi": "d3", "title": "t3"},
    ]
    with open(manifest, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pdf_path","md5","filesize","guess_year","lang","doi","title"])
        w.writeheader(); [w.writerow(r) for r in rows]

    # run make_split
    proc = subprocess.run(["python", "scripts/make_split.py", "--manifest", str(manifest), "--out_dir", str(out_dir)], capture_output=True, text=True)
    assert proc.returncode == 0
    assert (out_dir / "manifest_train.csv").exists()
    assert (out_dir / "manifest_val.csv").exists()
    assert (out_dir / "manifest_test.csv").exists()

