"""Response Generator Lambda - Sends WhatsApp responses.

Generates contextual, multilingual responses and sends them
to users via AWS End User Messaging Social.
"""

from common.exceptions import WhatsAppError
from common.logger import get_logger, log_context

logger = get_logger(__name__)


def handler(event, context):
    """Generate and send a WhatsApp response.

    Input: {
        "phone_number": str,
        "response_type": str,  # "welcome" | "ask_user_type" | "follow_up" | "matches" | "contact_exchange" | "error"
        "language": str,
        "data": dict
    }
    Output: {"statusCode": 200, "message_sent": bool}
    """
    phone_number = event.get("phone_number", "")
    response_type = event.get("response_type", "")
    language = event.get("language", "hi-IN")
    data = event.get("data", {})

    logger.info(
        "Generating response",
        extra=log_context(response_type=response_type, language=language),
    )

    try:
        from services.response_service import ResponseService

        response_service = ResponseService()
        response_service.send_response(
            phone_number=phone_number,
            response_type=response_type,
            language=language,
            data=data,
        )
        return {"statusCode": 200, "message_sent": True}
    except WhatsAppError as e:
        logger.exception("Failed to send response")
        return {"statusCode": 500, "message_sent": False, "error": str(e)}
