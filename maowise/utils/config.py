import os
from pathlib import Path
import yaml
from typing import Any, Dict


def load_config() -> Dict[str, Any]:
    cfg_file = os.environ.get("MAOWISE_CONFIG", "maowise/config/config.yaml")
    with open(cfg_file, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # ensure paths exist
    for key in ["data_raw", "data_parsed", "versions", "index_store", "reports"]:
        path = Path(cfg["paths"][key])
        path.mkdir(parents=True, exist_ok=True)
    Path(cfg["paths"].get("models_ckpt", "models_ckpt/fwd_v1")).mkdir(parents=True, exist_ok=True)
    # ensure nested under versions exists even when called before ingest
    (Path(cfg["paths"]["versions"]) / "maowise_ds_v1").mkdir(parents=True, exist_ok=True)

    return cfg

