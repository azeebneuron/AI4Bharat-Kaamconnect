"""Voice Processor Lambda - Handles voice message transcription.

Downloads audio from WhatsApp via EUMS, uploads to S3,
transcribes using Amazon Transcribe, then cleans up.
"""

from common.exceptions import LowConfidenceError, TranscriptionError
from common.logger import get_logger, log_context

logger = get_logger(__name__)


def handler(event, context):
    """Process a voice message.

    Input: {"media_id": str, "phone_number": str, "language_hint": str|None}
    Output: {"text": str, "language": str, "confidence": float} or error
    """
    media_id = event.get("media_id")
    phone_number = event.get("phone_number")
    language_hint = event.get("language_hint")

    if not media_id or not phone_number:
        logger.error("Missing required fields", extra=log_context(media_id=media_id))
        return {"statusCode": 400, "error": "media_id and phone_number are required"}

    logger.info(
        "Processing voice message",
        extra=log_context(media_id=media_id),
    )

    try:
        from services.voice_service import VoiceService

        voice_service = VoiceService()
        result = voice_service.process_voice_message(
            media_id=media_id,
            phone_number=phone_number,
            language_hint=language_hint,
        )
        return {"statusCode": 200, **result}
    except LowConfidenceError as e:
        logger.warning("Low confidence transcription", extra=log_context(error=str(e)))
        return {"statusCode": 200, "low_confidence": True, "error": str(e)}
    except TranscriptionError as e:
        logger.exception("Transcription failed")
        return {"statusCode": 500, "error": str(e)}
