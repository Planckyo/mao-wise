#!/usr/bin/env bash
set -euo pipefail
python -m maowise.kb.build_index --corpus datasets/data_parsed/corpus.jsonl --out_dir datasets/index_store || true
pytest -q

