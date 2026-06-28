import asyncio
import base64
import os
import uuid
import logging
import boto3

logger = logging.getLogger(__name__)


def _get_r2_client():
    account_id = os.getenv("CF_R2_ACCOUNT_ID")
    access_key = os.getenv("CF_R2_ACCESS_KEY_ID")
    secret_key = os.getenv("CF_R2_SECRET_ACCESS_KEY")
    if not account_id or not access_key or not secret_key:
        raise EnvironmentError("Missing Cloudflare R2 credentials")
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=endpoint,
    )


async def upload_detection_image(image_bytes: bytes, node_id: str, timestamp: str) -> str:
    bucket = os.getenv("CF_R2_BUCKET_NAME")
    public_url_base = os.getenv("CF_R2_PUBLIC_URL")
    if not bucket or not public_url_base:
        raise EnvironmentError("Missing Cloudflare R2 bucket configuration")

    object_key = f"detections/{node_id}/{timestamp}_{uuid.uuid4().hex}.jpg"

    def _upload() -> None:
        client = _get_r2_client()
        client.put_object(
            Bucket=bucket,
            Key=object_key,
            Body=image_bytes,
            ContentType="image/jpeg",
        )

    try:
        await asyncio.to_thread(_upload)
    except Exception:
        logger.exception("Failed to upload image to Cloudflare R2")
        raise

    return public_url_base.rstrip("/") + "/" + object_key
