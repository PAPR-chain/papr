import os
import sys
import json
import logging
import appdirs

IS_TEST = "unittest" in sys.modules

if IS_TEST:
    USERDATA_DIR = "/tmp/"
else:
    USERDATA_DIR = appdirs.user_data_dir("papr", "papr")

CHUNK_SIZE = 4096
ENCRYPTION_NUM_WORDS = 7

logger = logging.getLogger(__name__)


class Config:
    def __init__(self, submission_dir="", review_dir=""):
        self.submission_dir = submission_dir
        self.review_dir = review_dir
