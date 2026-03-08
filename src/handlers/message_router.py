"""Message Router Lambda - SNS triggered entry point.

Receives incoming WhatsApp messages via SNS, determines message type
and session state, then dispatches to appropriate processing Lambdas.
"""

import json

from common.logger import get_logger, log_context

logger = get_logger(__name__)


def handler(event, context):
    """Process SNS records containing WhatsApp webhook payloads."""
    logger.info("Received SNS event", extra=log_context(record_count=len(event.get("Records", []))))

    for record in event.get("Records", []):
        try:
            sns_message = json.loads(record["Sns"]["Message"])
            _process_message(sns_message)
        except Exception as e:
            # Don't re-raise: webhook already returned 200.
            # DLQ will catch persistent failures.
            logger.exception("Failed to process message", extra=log_context(error=str(e)))

    return {"statusCode": 200}


def _process_message(payload: dict) -> None:
    """Route a single message through the conversation state machine."""
    from services.routing_service import RoutingService

    routing_service = RoutingService()
    routing_service.process_message(payload)
