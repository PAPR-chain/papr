CHUNK_SIZE = 4096
ENCRYPTION_NUM_WORDS = 7

class Config:
    def __init__(self, submission_dir="", review_dir=""):
        self.submission_dir = submission_dir
        self.review_dir = review_dir
