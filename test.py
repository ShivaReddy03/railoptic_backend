# import base64
# import hashlib
# import os
# from Crypto.Cipher import AES
# from Crypto.Random import get_random_bytes

# import dotenv

# dotenv.load_dotenv()

# s=os.getenv("ORDER_ID_ENCRYPTION_KEY")
# SECRET_KEY = hashlib.sha256(b"upTIG5REoHkQ8NM7EfqfJg==").digest()[:16]
# print(SECRET_KEY)  # 128-bit AES key

# def encrypt_short(data: str) -> str:
#     iv = get_random_bytes(8)  # shorter IV for compactness (still safe if unique)
#     cipher = AES.new(SECRET_KEY, AES.MODE_CTR, nonce=iv)
#     ciphertext = cipher.encrypt(data.encode())
#     token = iv + ciphertext
#     b64 = base64.urlsafe_b64encode(token).decode().rstrip("=")
#     return b64[:45]  # usually ~35-40 chars

# def decrypt_short(token: str) -> str:
#     padded = token + '=' * (-len(token) % 4)
#     raw = base64.urlsafe_b64decode(padded)
#     iv, ciphertext = raw[:8], raw[8:]
#     cipher = AES.new(SECRET_KEY, AES.MODE_CTR, nonce=iv)
#     return cipher.decrypt(ciphertext).decode()

# # Example
# unit_id = "DEF-01-RMYCL-1025-UB1122"
# enc = encrypt_short(unit_id)
# dec = decrypt_short(enc)
# print(len(enc))
# print(f"Encrypted: {enc}")
# print(f"Decrypted: {dec}")


import base64
import hashlib
import os
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import dotenv

dotenv.load_dotenv()

# Get key from env
s = os.getenv("ORDER_ID_ENCRYPTION_KEY")
if not s:
    raise RuntimeError("Missing ORDER_ID_ENCRYPTION_KEY in environment")

# Convert to 16-byte AES key
SECRET_KEY = hashlib.sha256(s.encode("utf-8")).digest()[:16]
print(f"SECRET_KEY: {SECRET_KEY}")  # 128-bit AES key

def encrypt_short(data: str) -> str:
    iv = get_random_bytes(8)  # 64-bit nonce
    cipher = AES.new(SECRET_KEY, AES.MODE_CTR, nonce=iv)
    ciphertext = cipher.encrypt(data.encode())
    token = iv + ciphertext
    b64 = base64.urlsafe_b64encode(token).decode().rstrip("=")
    return b64[:45]  # truncate for compactness

def decrypt_short(token: str) -> str:
    padded = token + '=' * (-len(token) % 4)
    raw = base64.urlsafe_b64decode(padded)
    iv, ciphertext = raw[:8], raw[8:]
    cipher = AES.new(SECRET_KEY, AES.MODE_CTR, nonce=iv)
    return cipher.decrypt(ciphertext).decode()

# Example
unit_id = "DEF-01-RMYCL-1025-UB1122"
enc = encrypt_short(unit_id)
dec = decrypt_short(enc)

print(len(enc))
print(f"Encrypted: {enc}")
print(f"Decrypted: {dec}")
