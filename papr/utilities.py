import random
import hashlib
import rsa

from .constants import WORDS
from .settings import ENCRYPTION_NUM_WORDS, CHUNK_SIZE

def generate_human_readable_passphrase():
    return ' '.join(random.choices(WORDS, k=ENCRYPTION_NUM_WORDS))

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if chunk == b"":
                break
            h.update(chunk)
    return h.digest()

def rsa_encrypt_text(txt, pubkey):
    return rsa.encrypt(txt.encode('UTF-8'), pubkey)

def rsa_decrypt_text(data, private_key):
    #try:
    return rsa.decrypt(data, private_key)
    #except

