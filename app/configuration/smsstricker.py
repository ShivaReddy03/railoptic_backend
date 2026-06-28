import os
from dotenv import load_dotenv
import requests
import logging
import urllib.parse

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()


def send_otp_sms(phone_no: str, otp: str) -> bool:
    try:
        # SMS Striker API endpoint and credentials
        normalized_phone = phone_no.removeprefix("+91")
        username = os.getenv("SMS_USERNAME")
        password = os.getenv("SMS_PASSWORD")
        sender_id = os.getenv("SMS_SENDER_ID")
        template_id = os.getenv("SMS_TEMPLATE_ID")
        message = f"{otp} is OTP for login to Ramyaconstructions. OTP is valid for 90sec,  KapilGroup."

        # URL-encode the message to be safe
        encoded_msg = urllib.parse.quote(message)

        # Construct the full URL
        url = (
            "https://www.smsstriker.com/API/sms.php?"
            f"username={username}&password={password}&from={sender_id}"
            f"&to={normalized_phone}&msg={encoded_msg}&type=1&template_id={template_id}"
        )

        # Send the GET request
        response = requests.get(url)
        # Log URL and response
        logger.debug(f"SMS URL: {url}")
        logger.debug(f"Response Code: {response.status_code}")
        logger.debug(f"Response Body: {response.text}")

        # Send SMS Striker API
        if response.status_code == 200:
            body_text = response.text.lower()
            if "messages has been sent" in body_text or "ack" in body_text:
                return True
            else:
                logger.error(f"Failed to send OTP to {phone_no}: {response.text}")
                return False
        else:
            logger.error(
                f"Failed to send OTP to {phone_no}: HTTP {response.status_code}, {response.text}"
            )
            return False
    except Exception as e:
        logger.error(f"Error sending SMS to {phone_no}: {str(e)}")
        return False
