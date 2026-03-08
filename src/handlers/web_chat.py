"""Web Chat Lambda - HTTP API handler for web chat interface.

Receives POST /chat requests from API Gateway (Lambda proxy integration),
processes via WebChatService, returns JSON response.
"""

import json

from common.logger import get_logger

logger = get_logger(__name__)


def handler(event, context):
    """Handle web chat API request.

    API Gateway Lambda Proxy event:
    - POST /chat: {"session_id", "message", "audio_base64", "language"}
    - GET /chat: health check
    - OPTIONS: CORS preflight
    """
    http_method = event.get("httpMethod", "")

    cors_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    }

    if http_method == "OPTIONS":
        return {"statusCode": 200, "headers": cors_headers, "body": ""}

    if http_method == "GET":
        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": json.dumps({"status": "ok"}),
        }

    if http_method != "POST":
        return {
            "statusCode": 405,
            "headers": cors_headers,
            "body": json.dumps({"error": "Method not allowed"}),
        }

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "Invalid JSON"}),
        }

    session_id = body.get("session_id")
    message = body.get("message")
    audio_base64 = body.get("audio_base64")
    language = body.get("language")

    logger.info(
        "Web chat request",
        extra={
            "session_id": session_id,
            "has_text": bool(message),
            "has_audio": bool(audio_base64),
            "language": language,
        },
    )

    try:
        from services.web_chat_service import WebChatService

        service = WebChatService()
        result = service.process_message(
            session_id=session_id,
            text=message,
            audio_base64=audio_base64,
            language=language,
        )

        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": json.dumps(result, ensure_ascii=False, default=str),
        }
    except Exception as e:
        logger.exception("Web chat handler error")
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": "Internal server error"}),
        }
