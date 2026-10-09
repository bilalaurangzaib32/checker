import json
import os
from typing import Dict, Any, List

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "vps": {
        "host": "",
        "port": 22,
        "username": "root",
        "password": "",
        "private_key": "",
        "enabled": True
    },
    "discord": {
        "webhook_url": "",
        "enabled": True,
        "report_interval_hours": 6,
        "alert_on_recovery": True
    },
    "thresholds": {
        "cpu_percent": 85.0,
        "ram_percent": 90.0,
        "disk_percent": 90.0,
        "failed_ssh_attempts": 5
    },
    "websites": [
        # {"name": "Example Web", "url": "https://example.com", "expected_status": 200}
    ],
    "monitor_interval_seconds": 60,
    "last_report_timestamp": 0
}

def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with defaults for any missing keys
            config = DEFAULT_CONFIG.copy()
            for key, val in data.items():
                if isinstance(val, dict) and key in config and isinstance(config[key], dict):
                    config[key].update(val)
                else:
                    config[key] = val
            return config
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(config: Dict[str, Any]) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config.json: {e}")
