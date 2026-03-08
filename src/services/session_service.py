"""Session lifecycle management.

Handles session creation, state transitions, data accumulation,
and completeness checking for the conversational flow.
"""

from typing import Optional
from uuid import uuid4

from common.logger import get_logger, hash_phone, log_context
from common.models.session import ConversationState, Session
from common.repositories.session_repository import SessionRepository

logger = get_logger(__name__)

# Minimum required fields for matching (worker) or posting (employer)
WORKER_REQUIRED_FIELDS = ["job_type", "location"]
EMPLOYER_REQUIRED_FIELDS = ["job_type", "location", "salary"]


class SessionService:
    """Manages session lifecycle and conversation state."""

    def __init__(self, session_repo: Optional[SessionRepository] = None):
        self._repo = session_repo or SessionRepository()

    def get_or_create_session(self, phone_number: str) -> Session:
        """Get active session or create a new one."""
        session = self._repo.get_active_session(phone_number)
        if session and not session.is_expired():
            logger.info(
                "Found active session",
                extra=log_context(
                    phone_hash=hash_phone(phone_number),
                    session_id=session.session_id,
                    state=str(session.conversation_state),
                ),
            )
            return session

        # Create new session
        new_session = Session(
            phone_number=phone_number,
            session_id=str(uuid4()),
        )
        self._repo.create_session(new_session)
        logger.info(
            "Created new session",
            extra=log_context(
                phone_hash=hash_phone(phone_number),
                session_id=new_session.session_id,
            ),
        )
        return new_session

    def advance_state(
        self,
        session: Session,
        new_state: ConversationState,
        extracted_data_update: Optional[dict] = None,
    ) -> Session:
        """Advance session to a new state, optionally merging extracted data."""
        merged = self._merge_data(session.extracted_data, extracted_data_update or {})
        updated = self._repo.update_session_state(
            phone_number=session.phone_number,
            session_id=session.session_id,
            new_state=new_state,
            extracted_data=merged,
        )
        logger.info(
            "Advanced session state",
            extra=log_context(
                session_id=session.session_id,
                old_state=str(session.conversation_state),
                new_state=str(new_state),
            ),
        )
        return updated

    def set_user_type(self, session: Session, user_type: str) -> None:
        """Set the user type (worker/employer) for a session."""
        self._repo.update_user_type(session.phone_number, session.session_id, user_type)

    def set_language(self, session: Session, language: str) -> None:
        """Set the detected/selected language for a session."""
        self._repo.update_language(session.phone_number, session.session_id, language)

    def check_data_completeness(self, session: Session) -> tuple[bool, list[str]]:
        """Check if we have enough data to proceed with matching/posting.

        Returns (is_complete, list_of_missing_fields).
        """
        required = (
            WORKER_REQUIRED_FIELDS if session.user_type == "worker" else EMPLOYER_REQUIRED_FIELDS
        )
        extracted = session.extracted_data
        missing = []

        for field in required:
            value = extracted.get(field)
            if value is None:
                missing.append(field)
            elif isinstance(value, dict):
                # For nested fields like location, check if key sub-fields exist
                if field == "location" and not value.get("city"):
                    missing.append(field)

        return (len(missing) == 0, missing)

    def _merge_data(self, existing: dict, new: dict) -> dict:
        """Smart merge: new non-null values fill in gaps without overwriting existing data."""
        result = {**existing}
        for key, value in new.items():
            if value is None:
                continue
            if key not in result or result[key] is None:
                result[key] = value
            elif isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge_data(result[key], value)
            elif isinstance(value, list) and isinstance(result.get(key), list):
                # Merge lists, deduplicating
                existing_set = set(str(v).lower() for v in result[key])
                for item in value:
                    if str(item).lower() not in existing_set:
                        result[key].append(item)
            else:
                # New value overrides existing — allows user corrections
                result[key] = value
        return result
