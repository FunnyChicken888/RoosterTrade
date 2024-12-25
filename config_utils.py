import json
import os

CONFIG_PATH = 'config.json'

def load_config():
    """Load configuration from the config.json file."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as config_file:
            return json.load(config_file)
    else:
        raise FileNotFoundError("config.json not found. Please provide a valid configuration file.")

def update_config_value(key, value):
    """Update a specific key-value pair in the config.json file."""
    config = load_config()
    config[key] = value
    with open(CONFIG_PATH, 'w') as jsonfile:
        json.dump(config, jsonfile, indent=4)
