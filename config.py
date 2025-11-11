import json
from typing import Dict, Any

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "max_retries": 3,
    "backoff_base": 2,
    "storage_file": "queue.json",
    "lock_file": "queue.lock",
    "worker_heartbeat_seconds": 10,
    "worker_timeout_seconds": 30
}

def get_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                config.setdefault(key, value)
            return config
    except FileNotFoundError:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

def save_config(config: Dict[str, Any]):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)