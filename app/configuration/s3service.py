# S3 Service (app/configuration/s3service.py) - No changes needed, but added minor logging.
from datetime import datetime
import boto3
import uuid
import os
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from typing import Optional
from dotenv import load_dotenv
import logging
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()

class S3Service:
    def __init__(self):
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        self.access_key = os.getenv("AWS_ACCESS_KEY")
        self.secret_key = os.getenv("AWS_SECRET_KEY")
        self.region = os.getenv("AWS_REGION")
        self.endpoint = os.getenv("AWS_S3_ENDPOINT")

        if not all([self.bucket_name, self.access_key, self.secret_key, self.region, self.endpoint]):
            raise ValueError("Missing required AWS environment variables")

        session = boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )
        self.s3_client = session.client(
            "s3",
            endpoint_url=self.endpoint,
            config=boto3.session.Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    async def upload_file(self, file: UploadFile, doc_type: str) -> dict:
        try:
            allowed_extensions = [".jpg", ".jpeg", ".png", ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt"]
            file_extension = self._get_file_extension(file.filename).lower()

            if file_extension not in allowed_extensions:
                raise ValueError(f"Only {', '.join(allowed_extensions)} files are allowed")

            content = await file.read()
            if len(content) > 30 * 1024 * 1024:  # 20 MB limit
                raise ValueError("File size exceeds 20MB limit")

            file_name = f"agentdocs/{uuid.uuid4()}{file_extension}"

            await run_in_threadpool(
                self.s3_client.put_object,
                Bucket=self.bucket_name,
                Key=file_name,
                Body=content,
                ContentType=file.content_type or "application/octet-stream",
            )

            file_url = f"{self.endpoint.rstrip('/')}/{self.bucket_name}/{file_name}"

            return {
                "type": doc_type,
                "file_name": file.filename,
                "file_path": file_url,
                "status": "pending",
                "uploaded_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"S3 upload failed: {str(e)}", exc_info=True)
            raise

    async def delete_file(self, key: str) -> bool:
        try:
            prefix = f"{self.endpoint.rstrip('/')}/{self.bucket_name}/"
            if prefix in key:
                key = key.replace(prefix, "").strip("/")

            try:
                await run_in_threadpool(self.s3_client.head_object, Bucket=self.bucket_name, Key=key)
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    logger.warning(f"S3 object {key} not found in bucket {self.bucket_name}")
                    return False
                raise

            await run_in_threadpool(self.s3_client.delete_object, Bucket=self.bucket_name, Key=key)
            logger.debug(f"Successfully deleted S3 object: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete S3 file {key}: {str(e)}", exc_info=True)
            raise

    def _get_file_extension(self, filename: Optional[str]) -> str:
        if not filename:
            return ""
        return os.path.splitext(filename)[1]
    

s3_service = S3Service()