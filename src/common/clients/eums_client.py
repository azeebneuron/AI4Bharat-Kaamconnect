import json

import boto3

from common import config
from common.exceptions import MediaDownloadError, WhatsAppError
from common.logger import get_logger

logger = get_logger(__name__)


class EUMSClient:
    """Wrapper for AWS End User Messaging Social (WhatsApp) API."""

    def __init__(self):
        self._client = boto3.client("socialmessaging", region_name=config.EUMS_REGION)
        self._phone_number_arn = config.EUMS_PHONE_NUMBER_ARN

    @staticmethod
    def _normalize_phone(phone_number: str) -> str:
        """Ensure phone number has + prefix for E.164 format."""
        if not phone_number.startswith("+"):
            return f"+{phone_number}"
        return phone_number

    def send_text_message(self, phone_number: str, text: str) -> dict:
        """Send a text message to a WhatsApp user."""
        phone_number = self._normalize_phone(phone_number)
        message_payload = json.dumps({
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": text},
        })

        try:
            response = self._client.send_whatsapp_message(
                originationPhoneNumberId=self._phone_number_arn,
                message=message_payload.encode("utf-8"),
                metaApiVersion="v20.0",
            )
            logger.info("Sent text message via EUMS", extra={
                "message_id": response.get("messageId", ""),
                "http_status": response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""),
            })
            return response
        except Exception as e:
            raise WhatsAppError(f"Failed to send text message: {e}") from e

    def send_interactive_message(self, phone_number: str, interactive: dict) -> dict:
        """Send an interactive message (buttons or list) to a WhatsApp user."""
        phone_number = self._normalize_phone(phone_number)
        message_payload = json.dumps({
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": interactive,
        })

        try:
            response = self._client.send_whatsapp_message(
                originationPhoneNumberId=self._phone_number_arn,
                message=message_payload.encode("utf-8"),
                metaApiVersion="v20.0",
            )
            logger.info("Sent interactive message via EUMS")
            return response
        except Exception as e:
            raise WhatsAppError(f"Failed to send interactive message: {e}") from e

    def download_media(self, media_id: str, s3_bucket: str, s3_key: str) -> None:
        """Download media from WhatsApp via EUMS into S3.

        EUMS GetWhatsAppMessageMedia fetches media from Meta and stores it
        directly in the specified S3 location.
        """
        try:
            self._client.get_whatsapp_message_media(
                mediaId=media_id,
                originationPhoneNumberId=self._phone_number_arn,
                destinationS3File={
                    "bucketName": s3_bucket,
                    "key": s3_key,
                },
                metaApiVersion="v20.0",
            )
            logger.info("Downloaded media to S3 via EUMS", extra={
                "media_id": media_id, "s3_key": s3_key,
            })
        except Exception as e:
            raise MediaDownloadError(f"Failed to download media: {e}") from e
