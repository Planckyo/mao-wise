#!/usr/bin/env bash
set -e
python -m maowise.models.train_fwd --samples datasets/versions/maowise_ds_v1/samples.parquet \
  --model_name BAAI/bge-m3 --out_dir models_ckpt/fwd_v1 --epochs 8 --lr 2e-5 --batch 16

