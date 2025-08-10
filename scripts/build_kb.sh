#!/usr/bin/env bash
set -e
python -m maowise.kb.build_index --corpus datasets/data_parsed/corpus.jsonl --out_dir datasets/index_store

