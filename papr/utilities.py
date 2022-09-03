import os
import random
import hashlib
import logging
import base64

from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from coincurve import PrivateKey, PublicKey

from lbry.crypto.crypt import scrypt

from papr.constants import WORDS
from papr.config import ENCRYPTION_NUM_WORDS, CHUNK_SIZE

logger = logging.getLogger(__name__)


class DualLogger:
    def __init__(self, logger):
        self.logger = logger

    def debug(self, msg):
        self.logger.debug(msg)
        return {"debug": msg}

    def info(self, msg):
        self.logger.info(msg)
        return {"info": msg}

    def warning(self, msg):
        self.logger.warning(msg)
        return {"warning": msg}

    def error(self, msg):
        self.logger.error(msg)
        return {"error": msg}

    def critical(self, msg):
        self.logger.critical(msg)
        return {"error": msg}


def generate_human_readable_passphrase():
    return " ".join(random.choices(WORDS, k=ENCRYPTION_NUM_WORDS))


def read_all_bytes(path):
    data = b""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if chunk == b"":
                break
            data += chunk
    return data


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if chunk == b"":
                break
            h.update(chunk)
    return h.digest()


def rsa_encrypt_text(txt, pubkey):
    key = serialization.load_ssh_public_key(pubkey)
    return key.encrypt(
        txt.encode("UTF-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def rsa_decrypt_text(data: bytes, private_key: bytes, password: str):
    _password = password.encode("UTF-8")
    key = serialization.load_pem_private_key(private_key, _password)
    return key.decrypt(
        data,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    ).decode("UTF-8")


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


def generate_SECP256k1_keys(password: str):
    if password:
        private_key = PrivateKey(secret=password.encode())
    else:
        private_key = PrivateKey()

    public_key = private_key.public_key

    _private_key = base64.b64encode(private_key.to_pem()).decode()
    _public_key = base64.b64encode(public_key.format()).decode()

    if private_key.to_hex().count("0") >= 8:
        logger.warning(f"Possibly weak key generated!")

    return _private_key, _public_key


def SECP_encrypt_text(sender_private_key: str, recipient_public_key: str, msg: str):
    """
    Encrypts `msg` using AES256 and a shared secret generated with ECDH and two SECP256k1 keys as base64 strings
    """
    priv = PrivateKey.from_pem(base64.b64decode(sender_private_key.encode()))
    pub = PublicKey(base64.b64decode(recipient_public_key.encode()))
    shared_secret = priv.ecdh(pub.format())

    encrypted_msg = aes_encrypt_bytes(shared_secret, msg.encode()).decode()

    return encrypted_msg


def SECP_decrypt_text_from_hex(
    recipient_private_key: bytes, sender_public_key: str, encrypted_msg: str
):
    priv = PrivateKey.from_hex(recipient_private_key)
    pub = PublicKey(base64.b64decode(sender_public_key.encode()))
    return _SECP_decrypt_text(priv, pub, encrypted_msg)


def SECP_decrypt_text(
    recipient_private_key: str, sender_public_key: str, encrypted_msg: str
):
    priv = PrivateKey.from_pem(base64.b64decode(recipient_private_key.encode()))
    pub = PublicKey(base64.b64decode(sender_public_key.encode()))
    return _SECP_decrypt_text(priv, pub, encrypted_msg)


def _SECP_decrypt_text(priv: PrivateKey, pub: PublicKey, encrypted_msg: str):
    shared_secret = priv.ecdh(pub.format())

    msg = aes_decrypt_bytes(shared_secret, encrypted_msg.encode()).decode()

    return msg


# Based on github.com/lbryio/lbry-sdk/blob/master/lbry/crypto/crypt.py@6647dd
def aes_encrypt_bytes(secret: bytes, value: bytes) -> bytes:
    init_vector = os.urandom(16)
    key = scrypt(secret, salt=init_vector)
    encryptor = Cipher(AES(key), modes.CBC(init_vector), default_backend()).encryptor()
    padder = PKCS7(AES.block_size).padder()
    padded_data = padder.update(value) + padder.finalize()
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    return base64.b64encode(b"s:8192:16:1:" + init_vector + encrypted_data)


# Based on github.com/lbryio/lbry-sdk/blob/master/lbry/crypto/crypt.py@6647dd
def aes_decrypt_bytes(secret: bytes, value: bytes) -> bytes:
    try:
        data = base64.b64decode(value)
        _, scryp_n, scrypt_r, scrypt_p, data = data.split(b":", maxsplit=4)
        init_vector, data = data[:16], data[16:]
        key = scrypt(secret, init_vector, int(scryp_n), int(scrypt_r), int(scrypt_p))
        decryptor = Cipher(
            AES(key), modes.CBC(init_vector), default_backend()
        ).decryptor()
        unpadder = PKCS7(AES.block_size).unpadder()
        return unpadder.update(decryptor.update(data)) + unpadder.finalize()
    except ValueError as e:
        if e.args[0] == "Invalid padding bytes.":
            raise Exception("Invalid password")
        raise
