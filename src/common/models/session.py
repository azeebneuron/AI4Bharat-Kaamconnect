from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Optional

from common import config


class ConversationState(StrEnum):
    NEW = "new"
    AWAITING_USER_TYPE = "awaiting_user_type"
    AWAITING_PHONE_NUMBER = "awaiting_phone_number"
    AWAITING_LANGUAGE = "awaiting_language"
    COLLECTING_JOB_INFO = "collecting_job_info"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    MATCHING = "matching"
    VIEWING_MATCHES = "viewing_matches"
    CONTACT_EXCHANGE_PENDING = "contact_exchange_pending"
    COMPLETED = "completed"


@dataclass
class Session:
    phone_number: str
    session_id: str
    user_type: Optional[str] = None  # "worker" | "employer"
    language: Optional[str] = None  # Transcribe language code e.g. "hi-IN"
    conversation_state: ConversationState = ConversationState.NEW
    extracted_data: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    expires_at: int = 0  # epoch seconds

    def __post_init__(self):
        now = datetime.now(timezone.utc)
        if not self.created_at:
            self.created_at = now.isoformat()
        if not self.updated_at:
            self.updated_at = now.isoformat()
        if not self.expires_at:
            self.expires_at = int((now + timedelta(hours=config.SESSION_TTL_HOURS)).timestamp())

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc).timestamp() > self.expires_at

    def refresh_ttl(self) -> None:
        now = datetime.now(timezone.utc)
        self.updated_at = now.isoformat()
        self.expires_at = int((now + timedelta(hours=config.SESSION_TTL_HOURS)).timestamp())

    def to_dynamodb_item(self) -> dict:
        item = {
            "phone_number": self.phone_number,
            "session_id": self.session_id,
            "conversation_state": str(self.conversation_state),
            "extracted_data": self.extracted_data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }
        # DynamoDB rejects None values — only include optional fields when set
        if self.user_type is not None:
            item["user_type"] = self.user_type
        if self.language is not None:
            item["language"] = self.language
        return item

    @classmethod
    def from_dynamodb_item(cls, item: dict) -> "Session":
        return cls(
            phone_number=item["phone_number"],
            session_id=item["session_id"],
            user_type=item.get("user_type"),
            language=item.get("language"),
            conversation_state=ConversationState(item.get("conversation_state", "new")),
            extracted_data=item.get("extracted_data", {}),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
            expires_at=int(item.get("expires_at", 0)),
        )
