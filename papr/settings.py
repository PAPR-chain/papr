import json
import logging

CHUNK_SIZE = 4096
ENCRYPTION_NUM_WORDS = 7

logger = logging.getLogger(__name__)

class Config:
    def __init__(self, submission_dir="", review_dir=""):
        self.submission_dir = submission_dir
        self.review_dir = review_dir

    def load_from_json(self, path):
        try:
            data = json.loads(path)
        except json.JSONDecodeError:
            logger.error(f"Cannot decode configuration of {path}")
            return

        for k, v in data.items():
            setattr(self, k, v)

        logger.info(f"Configuration successfully loaded from {path}")
