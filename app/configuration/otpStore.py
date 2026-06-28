# import time
# import random
# import logging
# import bcrypt

# from app.configuration.smsstricker import send_otp_sms

# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

# # In-memory OTP storage
# otp_storage = {}

# def generate_otp() -> str:
#     return str(random.randint(100000, 999999))  # 6-digit OTP

# def store_otp(phone_no: str, otp: str) -> None:
#     # Store OTP with 5-minute expiry
#     expiry_time = time.time() + 300  # 300 seconds = 5 minutes
#     otp_storage[phone_no] = {"otp": otp, "expiry": expiry_time}
#     logger.debug(f"Stored OTP {otp} for {phone_no}")

# def verify_otp(phone_no: str, otp: str) -> bool:
#     if phone_no in otp_storage:
#         stored = otp_storage[phone_no]
#         if stored["expiry"] >= time.time() and stored["otp"] == otp:
#             del otp_storage[phone_no]  # Delete OTP after verification   
#             return True
#     return False


# def send_otp_service(phone_no: str) -> dict:
#     otp = generate_otp()
#     store_otp(phone_no, otp)

#     # send SMS
#     success = send_otp_sms(phone_no, otp)
#     if not success:
#         return {"status": "error", "message": "Failed to send OTP"}
#     return {"status": "success", "message": "OTP sent successfully"}

# # Hash password
# def hash_password(password: str) -> str:
#     return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# # Verify password
# def verify_password(plain_password: str, hashed_password: str) -> bool:
#     return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

import time
import random
import logging
import bcrypt

from app.configuration.smsstricker import send_otp_sms

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Hardcoded test credentials
HARDCODED_PHONE = "+919123456789"
HARDCODED_OTP = "000111"

# In-memory OTP storage
otp_storage = {}

def generate_otp() -> str:
    return str(random.randint(100000, 999999))  # 6-digit OTP

def store_otp(phone_no: str, otp: str) -> None:
    # Store OTP with 5-minute expiry
    expiry_time = time.time() + 300  # 300 seconds = 5 minutes
    otp_storage[phone_no] = {"otp": otp, "expiry": expiry_time}
    logger.debug(f"Stored OTP {otp} for {phone_no}")

def verify_otp(phone_no: str, otp: str) -> bool:
    # Check hardcoded credentials first (bypass for testing)
    if phone_no == HARDCODED_PHONE and otp == HARDCODED_OTP:
        logger.debug(f"Verified using hardcoded credentials for {phone_no}")
        return True
    
    # Original OTP verification logic
    if phone_no in otp_storage:
        stored = otp_storage[phone_no]
        if stored["expiry"] >= time.time() and stored["otp"] == otp:
            del otp_storage[phone_no]  # Delete OTP after verification   
            return True
    return False


def send_otp_service(phone_no: str) -> dict:
    # Skip sending SMS for hardcoded test number
    if phone_no == HARDCODED_PHONE:
        logger.debug(f"Skipping SMS send for hardcoded test number: {phone_no}")
        return {"status": "success", "message": "OTP sent successfully (test mode)"}
    
    # Original SMS sending logic
    otp = generate_otp()
    store_otp(phone_no, otp)

    # send SMS
    success = send_otp_sms(phone_no, otp)
    if not success:
        return {"status": "error", "message": "Failed to send OTP"}
    return {"status": "success", "message": "OTP sent successfully"}

# Hash password
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

# Verify password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))