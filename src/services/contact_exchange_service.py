"""Contact exchange workflow.

Manages the mutual consent process:
1. Worker expresses interest in a job match
2. Employer receives confirmation request
3. On confirmation, both parties receive each other's phone numbers
4. Match is recorded in both profiles
"""

import re
from datetime import datetime, timezone
from typing import Optional

from common.logger import get_logger, hash_phone, log_context
from common.models.session import ConversationState, Session
from common.repositories.job_posting_repository import JobPostingRepository
from common.repositories.user_profile_repository import UserProfileRepository
from services.response_service import ResponseService
from services.session_service import SessionService

logger = get_logger(__name__)


class ContactExchangeService:
    """Manages bidirectional contact exchange between workers and employers."""

    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        job_repo: Optional[JobPostingRepository] = None,
        profile_repo: Optional[UserProfileRepository] = None,
        response_service: Optional[ResponseService] = None,
    ):
        self._session_service = session_service or SessionService()
        self._job_repo = job_repo or JobPostingRepository()
        self._profile_repo = profile_repo or UserProfileRepository()
        self._response_service = response_service or ResponseService()

    def initiate_exchange(
        self,
        worker_phone: str,
        job_id: str,
        worker_session: Session,
    ) -> None:
        """Worker expresses interest - notify employer for confirmation."""
        posting = self._job_repo.get_posting(job_id)
        if not posting or posting.status != "active":
            self._response_service.send_response(
                phone_number=worker_phone,
                response_type="error",
                language=worker_session.language or "hi-IN",
                data={},
            )
            logger.warning("Job posting not available for exchange", extra=log_context(job_id=job_id))
            return

        employer_phone = posting.employer_phone

        # Store pending exchange in employer's session
        employer_session = self._session_service.get_or_create_session(employer_phone)
        self._session_service.advance_state(
            employer_session,
            ConversationState.CONTACT_EXCHANGE_PENDING,
            {
                "pending_worker_phone": worker_phone,
                "pending_job_id": job_id,
            },
        )

        # Notify employer
        self._response_service.send_response(
            phone_number=employer_phone,
            response_type="confirm_exchange",
            language=employer_session.language or "hi-IN",
            data={"worker_info": worker_session.extracted_data},
        )

        # Tell worker we're waiting for employer confirmation
        if (worker_session.language or "").startswith("hi"):
            text = "आपकी request employer को भेज दी गई है। जल्दी ही जवाब आएगा! ⏳"
        else:
            text = "Your request has been sent to the employer. You'll hear back soon! ⏳"

        from common.clients.eums_client import EUMSClient

        eums = EUMSClient()
        eums.send_text_message(worker_phone, text)

        logger.info(
            "Contact exchange initiated",
            extra=log_context(
                worker_hash=hash_phone(worker_phone),
                employer_hash=hash_phone(employer_phone),
                job_id=job_id,
            ),
        )

    @staticmethod
    def _is_valid_phone(phone: str) -> bool:
        """Validate E.164 phone number format."""
        return bool(re.fullmatch(r"\+\d{10,15}", phone))

    def confirm_exchange(self, employer_phone: str, employer_session: Session) -> None:
        """Employer confirms - exchange contact details."""
        worker_phone = employer_session.extracted_data.get("pending_worker_phone")
        job_id = employer_session.extracted_data.get("pending_job_id")

        if not worker_phone or not job_id:
            logger.error("Missing exchange data in employer session")
            return

        # Validate phone numbers before sharing
        if not self._is_valid_phone(worker_phone) or not self._is_valid_phone(employer_phone):
            logger.error(
                "Invalid phone number format in exchange",
                extra=log_context(
                    worker_valid=self._is_valid_phone(worker_phone),
                    employer_valid=self._is_valid_phone(employer_phone),
                ),
            )
            return

        # Idempotency: clear pending data first to prevent double-exchange
        # If another concurrent invocation already cleared this, we'll detect it above
        self._session_service.advance_state(
            employer_session,
            ConversationState.COMPLETED,
            {"pending_worker_phone": None, "pending_job_id": None},
        )

        # Send worker's number to employer
        self._response_service.send_response(
            phone_number=employer_phone,
            response_type="contact_shared",
            language=employer_session.language or "hi-IN",
            data={"contact_number": worker_phone},
        )

        # Send employer's number to worker
        worker_session = self._session_service.get_or_create_session(worker_phone)
        self._response_service.send_response(
            phone_number=worker_phone,
            response_type="contact_shared",
            language=worker_session.language or "hi-IN",
            data={"contact_number": employer_phone},
        )

        # Record match in both profiles
        match_record = {
            "job_id": job_id,
            "matched_at": datetime.now(timezone.utc).isoformat(),
            "status": "exchanged",
        }
        self._profile_repo.add_match_to_history(worker_phone, match_record)
        self._profile_repo.add_match_to_history(employer_phone, match_record)

        # Worker session to completed
        self._session_service.advance_state(worker_session, ConversationState.COMPLETED)

        logger.info(
            "Contact exchange completed",
            extra=log_context(
                worker_hash=hash_phone(worker_phone),
                employer_hash=hash_phone(employer_phone),
                job_id=job_id,
            ),
        )

    def reject_exchange(self, employer_phone: str, employer_session: Session) -> None:
        """Employer rejects the exchange."""
        worker_phone = employer_session.extracted_data.get("pending_worker_phone")

        # Notify worker
        if worker_phone:
            worker_session = self._session_service.get_or_create_session(worker_phone)
            lang = worker_session.language or "hi-IN"
            if lang.startswith("hi"):
                text = "Employer ने अभी interest नहीं दिखाया। अन्य jobs देखने के लिए फिर से बात करें। 🙏"
            else:
                text = "The employer is not interested at this time. Talk to us again to see other jobs. 🙏"

            from common.clients.eums_client import EUMSClient

            eums = EUMSClient()
            eums.send_text_message(worker_phone, text)

            # Reset worker session to viewing matches
            self._session_service.advance_state(worker_session, ConversationState.VIEWING_MATCHES)

        # Reset employer session
        self._session_service.advance_state(employer_session, ConversationState.COMPLETED)

        logger.info("Contact exchange rejected", extra=log_context(employer_hash=hash_phone(employer_phone)))
