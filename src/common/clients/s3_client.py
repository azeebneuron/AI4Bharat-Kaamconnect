import hashlib
from uuid import uuid4

import boto3

from common import config
from common.logger import get_logger

logger = get_logger(__name__)


class S3Client:
    """Wrapper for S3 operations on voice files."""

    def __init__(self):
        self._s3 = boto3.client("s3", region_name=config.REGION)
        self._bucket = config.S3_VOICE_BUCKET

    @property
    def bucket_name(self) -> str:
        return self._bucket

    def upload_voice_file(self, key: str, audio_bytes: bytes, content_type: str = "audio/ogg") -> str:
        """Upload voice file to S3. Returns the S3 URI."""
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=audio_bytes,
            ContentType=content_type,
        )
        s3_uri = f"s3://{self._bucket}/{key}"
        logger.info("Uploaded voice file to S3", extra={"s3_uri": s3_uri})
        return s3_uri

    def delete_voice_file(self, key: str) -> None:
        """Delete voice file from S3. Must be called after transcription (Req 9.2)."""
        self._s3.delete_object(Bucket=self._bucket, Key=key)
        logger.info("Deleted voice file from S3")

    def generate_voice_key(self, phone_number: str) -> str:
        """Generate a unique S3 key for a voice file."""
        phone_hash = hashlib.sha256(phone_number.encode()).hexdigest()[:12]
        return f"voice/{phone_hash}/{uuid4().hex[:8]}.ogg"

    def get_s3_uri(self, key: str) -> str:
        """Get the S3 URI for a key."""
        return f"s3://{self._bucket}/{key}"
