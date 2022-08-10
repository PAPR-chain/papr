import random
import hashlib
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

from .constants import WORDS
from .settings import ENCRYPTION_NUM_WORDS, CHUNK_SIZE

def generate_human_readable_passphrase():
    return ' '.join(random.choices(WORDS, k=ENCRYPTION_NUM_WORDS))

def read_all_bytes(path):
    data = b""
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if chunk == b"":
                break
            data += chunk
    return data

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
    key = serialization.load_ssh_public_key(pubkey)
    return key.encrypt(txt.encode('UTF-8'),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )

def rsa_decrypt_text(data: bytes, private_key: bytes, password: str):
    _password = password.encode('UTF-8')
    key = serialization.load_pem_private_key(private_key, _password)
    return key.decrypt(data,
            padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    ).decode('UTF-8')

def generate_rsa_keys(password: str):
    key = rsa.generate_private_key(
        backend=default_backend(), public_exponent=65537, key_size=2048
    )

    public_key = key.public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
    )

    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(
            password.encode("UTF-8")
        ),
    )

    return pem, public_key

