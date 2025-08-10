import argparse
from maowise.kb.build_index import build_index


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out_dir", required=True)
    args = parser.parse_args()
    build_index(args.corpus, args.out_dir)

