import json

from papr.settings import Config

def load_manuscript(name):
    pass

def load_config(path):
    try:
        data = json.loads(path)
    except json.JSONDecodeError:
        logger.error(f"Cannot decode configuration of {path}")
        return

    config = Config()

    for k, v in data.items():
        setattr(config, k, v)

    logger.info(f"Configuration successfully loaded from {path}")
    return config
