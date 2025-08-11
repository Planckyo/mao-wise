import argparse, csv, json, random
from pathlib import Path


def year_bin(y):
    if y is None:
        return "unknown"
    if y <= 2010:
        return "<=2010"
    if y <= 2016:
        return "2011-2016"
    if y <= 2020:
        return "2017-2020"
    return "2021-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--ratio", nargs=3, type=float, default=[0.7, 0.15, 0.15])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out_dir", default="manifests")
    args = ap.parse_args()

    random.seed(args.seed)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    with open(args.manifest, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r["guess_year"] = int(r["guess_year"]) if r.get("guess_year") else None
            rows.append(r)

    buckets = {}
    for r in rows:
        buckets.setdefault(year_bin(r["guess_year"]), []).append(r)

    train, val, test = [], [], []
    for b, items in buckets.items():
        random.shuffle(items)
        n = len(items)
        n_train = int(round(args.ratio[0] * n))
        n_val = int(round(args.ratio[1] * n))
        n_test = n - n_train - n_val
        train += items[:n_train]
        val += items[n_train : n_train + n_val]
        test += items[n_train + n_val :]

    def dump(name, arr):
        p = out_dir / f"manifest_{name}.csv"
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "pdf_path",
                    "md5",
                    "filesize",
                    "guess_year",
                    "lang",
                    "doi",
                    "title",
                ],
            )
            w.writeheader()
            for r in arr:
                w.writerow(r)
        return str(p)

    ptrain, pval, ptest = dump("train", train), dump("val", val), dump("test", test)
    meta = {
        "seed": args.seed,
        "ratio": args.ratio,
        "counts": {"train": len(train), "val": len(val), "test": len(test)},
        "bins": {b: len(v) for b, v in buckets.items()},
    }
    with (out_dir / "split_meta.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("[OK] split ->", ptrain, pval, ptest)


if __name__ == "__main__":
    main()

