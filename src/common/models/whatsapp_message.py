import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class InboundMessage:
    """Parsed inbound WhatsApp message from EUMS webhook."""

    message_id: str
    phone_number: str  # sender E.164 format
    message_type: str  # "text" | "audio" | "image" | "interactive"
    text_body: Optional[str] = None
    media_id: Optional[str] = None
    timestamp: str = ""

    # For interactive replies (button/list selection)
    interactive_type: Optional[str] = None  # "button_reply" | "list_reply"
    interactive_id: Optional[str] = None  # the selected button/row ID
    interactive_title: Optional[str] = None  # the selected button/row title

    @classmethod
    def from_webhook_payload(cls, payload: dict) -> "InboundMessage":
        """Parse EUMS SNS webhook payload into structured message.

        EUMS payload structure:
        {
            "context": {...},
            "whatsAppWebhookEntry": "<JSON string with WhatsApp Cloud API payload>",
            ...
        }

        The whatsAppWebhookEntry contains:
        {"id": "...", "changes": [{"value": {"messages": [...]}, "field": "messages"}]}
        """
        # Extract message from EUMS wrapper
        message = cls._extract_message(payload)

        message_type = message.get("type", "text")

        text_body = None
        media_id = None
        interactive_type = None
        interactive_id = None
        interactive_title = None

        if message_type == "text":
            text_body = message.get("text", {}).get("body", "")
        elif message_type == "audio":
            media_id = message.get("audio", {}).get("id", "")
        elif message_type == "interactive":
            interactive = message.get("interactive", {})
            interactive_type = interactive.get("type")
            if interactive_type == "button_reply":
                reply = interactive.get("button_reply", {})
                interactive_id = reply.get("id")
                interactive_title = reply.get("title")
            elif interactive_type == "list_reply":
                reply = interactive.get("list_reply", {})
                interactive_id = reply.get("id")
                interactive_title = reply.get("title")

        return cls(
            message_id=message.get("id", ""),
            phone_number=message.get("from", ""),
            message_type=message_type,
            text_body=text_body,
            media_id=media_id,
            timestamp=message.get("timestamp", ""),
            interactive_type=interactive_type,
            interactive_id=interactive_id,
            interactive_title=interactive_title,
        )

    @staticmethod
    def _extract_message(payload: dict) -> dict:
        """Extract the WhatsApp message dict from EUMS or direct payload.

        Returns empty dict for non-message events (status updates, read receipts).
        """
        # EUMS format: whatsAppWebhookEntry is a JSON string
        webhook_entry = payload.get("whatsAppWebhookEntry")
        if webhook_entry:
            if isinstance(webhook_entry, str):
                webhook_entry = json.loads(webhook_entry)
            changes = webhook_entry.get("changes", [])
            if changes:
                value = changes[0].get("value", {})
                messages = value.get("messages", [])
                if messages:
                    return messages[0]
            # No messages — this is a status update, not a user message
            return {}

        # Direct WhatsApp Cloud API format (via API Gateway webhook)
        entry = payload.get("entry", [])
        if entry:
            changes = entry[0].get("changes", [])
            if changes:
                value = changes[0].get("value", {})
                messages = value.get("messages", [])
                if messages:
                    return messages[0]

        # Fallback: payload is the message itself
        return payload.get("message", payload)


@dataclass
class OutboundMessage:
    """Outbound WhatsApp message to send via EUMS."""

    phone_number: str  # recipient E.164 format
    message_type: str = "text"  # "text" | "interactive"
    text_body: Optional[str] = None
    interactive_payload: Optional[dict] = None

    def to_eums_payload(self) -> dict:
        """Convert to EUMS WhatsApp send message format."""
        payload: dict = {
            "messaging_product": "whatsapp",
            "to": self.phone_number,
            "type": self.message_type,
        }

        if self.message_type == "text":
            payload["text"] = {"body": self.text_body}
        elif self.message_type == "interactive":
            payload["interactive"] = self.interactive_payload

        return payload
