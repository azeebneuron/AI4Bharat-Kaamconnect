import time
from uuid import uuid4

import boto3

from common import config
from common.exceptions import TranscriptionError
from common.logger import get_logger

logger = get_logger(__name__)


class TranscribeClient:
    """Wrapper for Amazon Transcribe batch transcription."""

    # Polling intervals in seconds (exponential backoff, ~55s total)
    POLL_INTERVALS = [1, 2, 3, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5]

    def __init__(self):
        self._transcribe = boto3.client("transcribe", region_name=config.REGION)

    def start_transcription(
        self, s3_uri: str, language_code: str | None = None,
        job_name: str | None = None, media_format: str = "ogg",
    ) -> str:
        """Start a transcription job. Returns the job name.

        If language_code is None, auto-detects from all supported Indian languages.
        """
        if not job_name:
            job_name = f"kc-{uuid4().hex[:8]}"

        kwargs: dict = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": s3_uri},
            "MediaFormat": media_format,
        }

        if language_code:
            kwargs["LanguageCode"] = language_code
        else:
            # Auto-detect from supported languages
            kwargs["IdentifyLanguage"] = True
            kwargs["LanguageOptions"] = list(config.SUPPORTED_LANGUAGES.values())

        self._transcribe.start_transcription_job(**kwargs)
        logger.info("Started transcription job", extra={"job_name": job_name})
        return job_name

    def get_transcription_result(self, job_name: str, timeout_seconds: int = 60) -> dict:
        """Poll for transcription result with exponential backoff.

        Returns: {"text": str, "confidence": float, "language": str}
        """
        elapsed = 0.0
        for interval in self.POLL_INTERVALS:
            if elapsed >= timeout_seconds:
                break
            time.sleep(interval)
            elapsed += interval

            response = self._transcribe.get_transcription_job(TranscriptionJobName=job_name)
            job = response["TranscriptionJob"]
            status = job["TranscriptionJobStatus"]

            if status == "COMPLETED":
                return self._parse_result(job)
            elif status == "FAILED":
                reason = job.get("FailureReason", "Unknown")
                raise TranscriptionError(f"Transcription failed: {reason}")

        raise TranscriptionError(f"Transcription timed out after {timeout_seconds}s")

    def _parse_result(self, job: dict) -> dict:
        """Parse completed transcription job into structured result."""
        transcript_uri = job["Transcript"]["TranscriptFileUri"]

        # Fetch the transcript JSON from the URI
        import json
        import urllib.request

        with urllib.request.urlopen(transcript_uri, timeout=10) as response:
            transcript_data = json.loads(response.read().decode())

        results = transcript_data.get("results", {})
        transcripts = results.get("transcripts", [])
        text = transcripts[0]["transcript"] if transcripts else ""

        # Calculate average confidence from items
        items = results.get("items", [])
        confidences = [
            float(alt["confidence"])
            for item in items
            for alt in item.get("alternatives", [])
            if "confidence" in alt
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Get detected language
        language = job.get("LanguageCode", "")
        if not language and "IdentifiedLanguageScore" in job:
            # When using IdentifyLanguage
            language = job.get("LanguageCode", "hi-IN")

        logger.info(
            "Transcription completed",
            extra={"confidence": f"{avg_confidence:.2f}", "language": language},
        )

        return {
            "text": text,
            "confidence": avg_confidence,
            "language": language,
        }

    def cleanup_job(self, job_name: str) -> None:
        """Delete a completed transcription job."""
        try:
            self._transcribe.delete_transcription_job(TranscriptionJobName=job_name)
        except Exception:
            pass  # Best-effort cleanup
