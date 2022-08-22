import os
import sys
import json
import logging
import appdirs

from lbry.conf import Config as LbryConfig
from lbry.conf import Path

IS_TEST = "unittest" in sys.modules

if IS_TEST:
    USERDATA_DIR = "/tmp/"
else:
    USERDATA_DIR = appdirs.user_data_dir("papr", "papr")

CHUNK_SIZE = 4096
ENCRYPTION_NUM_WORDS = 7

logger = logging.getLogger(__name__)


class Config(LbryConfig):
    review_dir = Path("Directory path to store submitted reviews", metavar="DIR")

    submission_dir = Path(
        "Directory path to store submitted manuscripts", metavar="DIR"
    )

    database_dir = Path(
        "Directory containing the database storing cached and private information",
        metavar="DIR",
    )
