from datetime import datetime, timedelta, timezone
from typing import Optional

from boto3.dynamodb.conditions import Attr, Key

from common import config
from common.logger import get_logger
from common.models.session import ConversationState, Session
from common.repositories.base_repository import BaseRepository

logger = get_logger(__name__)


class SessionRepository(BaseRepository):
    """Repository for session management in DynamoDB."""

    def __init__(self):
        super().__init__(config.SESSIONS_TABLE)

    def get_active_session(self, phone_number: str) -> Optional[Session]:
        """Get the most recent non-expired session for a phone number."""
        items = self.query_with_key(
            partition_key_name="phone_number",
            partition_key_value=phone_number,
        )
        if not items:
            return None

        # Sort by created_at descending to get the most recent session
        # (sort key is UUID which has no time ordering)
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        for item in items:
            session = Session.from_dynamodb_item(item)
            if not session.is_expired():
                return session
        return None

    def create_session(self, session: Session) -> None:
        """Create a new session."""
        self.put_item(session.to_dynamodb_item())
        logger.info(
            "Created new session",
            extra={"session_id": session.session_id},
        )

    def update_session_state(
        self,
        phone_number: str,
        session_id: str,
        new_state: ConversationState,
        extracted_data: Optional[dict] = None,
    ) -> Session:
        """Atomically update session state, extracted data, and refresh TTL."""
        now = datetime.now(timezone.utc)
        new_expires = int((now + timedelta(hours=config.SESSION_TTL_HOURS)).timestamp())

        updates = {
            "conversation_state": str(new_state),
            "updated_at": now.isoformat(),
            "expires_at": new_expires,
        }
        if extracted_data is not None:
            updates["extracted_data"] = extracted_data

        updated = self.update_item(
            key={"phone_number": phone_number, "session_id": session_id},
            updates=updates,
        )
        return Session.from_dynamodb_item(updated)

    def update_language(self, phone_number: str, session_id: str, language: str) -> None:
        """Update the detected/selected language for a session."""
        self.update_item(
            key={"phone_number": phone_number, "session_id": session_id},
            updates={"language": language},
        )

    def update_user_type(self, phone_number: str, session_id: str, user_type: str) -> None:
        """Update the user type (worker/employer) for a session."""
        self.update_item(
            key={"phone_number": phone_number, "session_id": session_id},
            updates={"user_type": user_type},
        )
