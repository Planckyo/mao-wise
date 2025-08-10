import argparse
from maowise.models.train_fwd import train


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True)
    parser.add_argument("--model_name", default="BAAI/bge-m3")
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()
    train(args.samples, args.out_dir, model_name=args.model_name)

