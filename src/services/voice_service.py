"""Voice processing pipeline.

Orchestrates: download from WhatsApp -> S3 upload -> Transcribe -> S3 delete.
Voice files are ALWAYS deleted after transcription (Req 9.2).
"""

from typing import Optional

from common.clients.eums_client import EUMSClient
from common.clients.s3_client import S3Client
from common.clients.transcribe_client import TranscribeClient
from common.exceptions import LowConfidenceError, TranscriptionError
from common.logger import get_logger, hash_phone, log_context

logger = get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.90


class VoiceService:
    """Processes voice messages through the transcription pipeline."""

    def __init__(
        self,
        eums_client: Optional[EUMSClient] = None,
        s3_client: Optional[S3Client] = None,
        transcribe_client: Optional[TranscribeClient] = None,
    ):
        self._eums = eums_client or EUMSClient()
        self._s3 = s3_client or S3Client()
        self._transcribe = transcribe_client or TranscribeClient()

    def process_voice_message(
        self,
        media_id: str,
        phone_number: str,
        language_hint: Optional[str] = None,
    ) -> dict:
        """Process a voice message end-to-end.

        Returns: {"text": str, "language": str, "confidence": float}
        Raises: LowConfidenceError if confidence < 90%, TranscriptionError on failure.
        """
        phone_hash = hash_phone(phone_number)
        s3_key = self._s3.generate_voice_key(phone_number)

        logger.info(
            "Starting voice processing",
            extra=log_context(phone_hash=phone_hash, media_id=media_id),
        )

        # 1. Download audio from WhatsApp directly into S3
        bucket = self._s3.bucket_name
        self._eums.download_media(media_id, bucket, s3_key)
        s3_uri = f"s3://{bucket}/{s3_key}"
        logger.info("Downloaded audio to S3 via EUMS", extra=log_context(s3_key=s3_key))

        job_name = None
        try:
            # 3. Start transcription
            job_name = self._transcribe.start_transcription(
                s3_uri=s3_uri,
                language_code=language_hint,
            )

            # 4. Wait for result
            result = self._transcribe.get_transcription_result(job_name)

            # 5. Check confidence
            if result["confidence"] < CONFIDENCE_THRESHOLD:
                raise LowConfidenceError(
                    f"Transcription confidence {result['confidence']:.2f} is below "
                    f"threshold {CONFIDENCE_THRESHOLD}"
                )

            logger.info(
                "Voice processing complete",
                extra=log_context(
                    phone_hash=phone_hash,
                    language=result["language"],
                    confidence=f"{result['confidence']:.2f}",
                    text_length=len(result["text"]),
                ),
            )

            return result

        finally:
            # 6. ALWAYS delete voice file from S3 (Req 9.2)
            self._s3.delete_voice_file(s3_key)
            # Clean up transcription job if it was started
            if job_name is not None:
                self._transcribe.cleanup_job(job_name)
