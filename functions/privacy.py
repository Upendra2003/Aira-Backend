from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from base64 import b64encode, b64decode
import os

# Generate a 256-bit (32-byte) secret key — store this securely in env or vault
SECRET_KEY = os.environ.get("ENCRYPTION_KEY", os.urandom(32))  # 32 bytes for AES-256

# Encrypt Function
def encrypt_message(plain_text):
    iv = os.urandom(16)  # 16 bytes for AES block size
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plain_text.encode()) + padder.finalize()

    cipher = Cipher(algorithms.AES(SECRET_KEY), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded_data) + encryptor.finalize()

    return {
        'iv': b64encode(iv).decode(),
        'content': b64encode(encrypted).decode()
    }

# Decrypt Function
def decrypt_message(iv_b64, encrypted_b64):
    iv = b64decode(iv_b64)
    encrypted_data = b64decode(encrypted_b64)

    cipher = Cipher(algorithms.AES(SECRET_KEY), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_padded = decryptor.update(encrypted_data) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()

    return decrypted.decode()
