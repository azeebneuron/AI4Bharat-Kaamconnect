"""Entity Extractor Lambda - Extracts structured job info from text.

Uses Amazon Bedrock Claude Haiku to extract job type, location,
salary, skills, and availability from natural language text.
"""

from common.exceptions import ExtractionError
from common.logger import get_logger, log_context

logger = get_logger(__name__)


def handler(event, context):
    """Extract entities from text.

    Input: {"text": str, "session": dict, "user_type": str}
    Output: {"extracted_entities": dict, "follow_up": str|None, "confidence": float}
    """
    text = event.get("text", "")
    session_data = event.get("session", {})
    user_type = event.get("user_type", "worker")

    logger.info("Extracting entities from text", extra=log_context(text_length=len(text)))

    try:
        from services.extraction_service import ExtractionService

        extraction_service = ExtractionService()
        result = extraction_service.extract_entities(
            text=text,
            session_data=session_data,
            user_type=user_type,
        )
        return {"statusCode": 200, **result}
    except ExtractionError as e:
        logger.exception("Entity extraction failed")
        return {"statusCode": 500, "error": str(e)}
