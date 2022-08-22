import json

from papr.settings import Config


class PaprObject:

    SAVED_FIELDS = []
    LOADED_FIELDS = []

    def __init__(self):
        raise Exception("Initiator unimplemented")

    @classmethod
    def from_json(cls, **kwargs):
        base_params = {}
        for a, v in cls.SAVED_FIELDS.items():
            if a not in kwargs:
                raise Exception(
                    f"JSON data for initiation of {type(self)}) is missing field {a}"
                )
            base_params[a] = v

        obj = cls(**base_params)

        for a, v in cls.LOADED_FIELDS.items():
            if a in kwargs:
                setattr(obj, a, v)

        return obj

    def to_json(self):
        d = {}
        for a in self.SAVED_FIELDS:
            d[a] = getattr(self, a)
        return d


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
