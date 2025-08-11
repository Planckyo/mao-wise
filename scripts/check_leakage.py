import argparse, sys
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", required=True)
    args = ap.parse_args()
    df = pd.read_parquet(args.samples)
    if "split" not in df.columns:
        print("[ERR] 'split' column missing", file=sys.stderr)
        sys.exit(2)

    keys = {}
    for sp in df["split"].dropna().unique():
        sub = df[df["split"] == sp]
        s = set(zip(sub.get("source_pdf", [""]), sub.get("md5", [""]), sub.get("doi", [""])))
        keys[sp] = s
    splits = list(keys)
    for i in range(len(splits)):
        for j in range(i + 1, len(splits)):
            a, b = splits[i], splits[j]
            inter = keys[a] & keys[b]
            if inter:
                print(f"[ERR] leakage between {a} and {b}: {len(inter)} docs", file=sys.stderr)
                for k in list(inter)[:5]:
                    print("  ", k, file=sys.stderr)
                sys.exit(3)
    summ = df.groupby("split").agg(n_samples=("sample_id", "count"), n_docs=("source_pdf", "nunique")).reset_index()
    print(summ.to_string(index=False))
    print("[OK] leakage check passed")


if __name__ == "__main__":
    main()

