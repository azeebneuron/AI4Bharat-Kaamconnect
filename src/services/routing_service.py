"""Message routing and conversation state machine.

Central orchestrator that receives parsed WhatsApp messages,
manages session state, and dispatches to appropriate services.
"""

import json
from typing import Optional

import boto3

from common import config
from common.exceptions import LowConfidenceError, RateLimitError
from common.logger import get_logger, hash_phone, log_context
from common.models.session import ConversationState, Session
from common.models.whatsapp_message import InboundMessage
from services.session_service import SessionService

logger = get_logger(__name__)


class RoutingService:
    """Routes incoming messages through the conversation state machine."""

    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        lambda_client=None,
    ):
        self._session_service = session_service or SessionService()
        self._lambda = lambda_client or boto3.client("lambda", region_name=config.REGION)

    def process_message(self, sns_payload: dict) -> None:
        """Process a single incoming WhatsApp message."""
        message = InboundMessage.from_webhook_payload(sns_payload)

        # Skip non-message events (status updates, read receipts)
        if not message.phone_number:
            logger.debug("Skipping non-message event (no phone number)")
            return

        phone_hash = hash_phone(message.phone_number)

        logger.info(
            "Processing message",
            extra=log_context(
                phone_hash=phone_hash,
                message_type=message.message_type,
                correlation_id=message.message_id,
            ),
        )

        session = self._session_service.get_or_create_session(message.phone_number)

        # State machine dispatch
        state = session.conversation_state
        try:
            if state == ConversationState.NEW:
                self._handle_new_user(message, session)
            elif state == ConversationState.AWAITING_USER_TYPE:
                self._handle_user_type_selection(message, session)
            elif state == ConversationState.AWAITING_LANGUAGE:
                self._handle_language_selection(message, session)
            elif state in (ConversationState.COLLECTING_JOB_INFO, ConversationState.AWAITING_CONFIRMATION):
                self._handle_job_info(message, session)
            elif state == ConversationState.MATCHING:
                # Matching in progress, ask user to wait
                self._send_response(
                    phone_number=message.phone_number,
                    response_type="please_wait",
                    language=session.language or "hi-IN",
                    data={},
                )
            elif state == ConversationState.VIEWING_MATCHES:
                self._handle_match_selection(message, session)
            elif state == ConversationState.CONTACT_EXCHANGE_PENDING:
                self._handle_exchange_confirmation(message, session)
            elif state == ConversationState.COMPLETED:
                # User is starting over
                self._handle_new_user(message, session)
            else:
                self._handle_job_info(message, session)
        except Exception as e:
            logger.exception(
                "Error processing message",
                extra=log_context(phone_hash=phone_hash, error=str(e)),
            )
            self._send_error_response(message.phone_number, session.language or "hi-IN")

    def _handle_new_user(self, message: InboundMessage, session: Session) -> None:
        """Welcome new user and ask for user type."""
        # If they sent a voice/text message right away, we can try to detect language
        # and process it. For now, send welcome and ask user type.
        self._session_service.advance_state(session, ConversationState.AWAITING_USER_TYPE)
        self._send_response(
            phone_number=message.phone_number,
            response_type="welcome",
            language=session.language or "hi-IN",
            data={},
        )

    def _handle_user_type_selection(self, message: InboundMessage, session: Session) -> None:
        """Process user type selection (worker/employer)."""
        user_type = None

        if message.message_type == "interactive" and message.interactive_id:
            user_type = message.interactive_id  # "worker" or "employer"
        elif message.text_body:
            text = message.text_body.strip().lower()
            if text in ("worker", "kaamgar", "kaam", "1", "majdoor"):
                user_type = "worker"
            elif text in ("employer", "malik", "2", "niyokta"):
                user_type = "employer"

        if user_type:
            self._session_service.set_user_type(session, user_type)
            session.user_type = user_type
            self._session_service.advance_state(session, ConversationState.COLLECTING_JOB_INFO)
            self._send_response(
                phone_number=message.phone_number,
                response_type="ask_job_details",
                language=session.language or "hi-IN",
                data={"user_type": user_type},
            )
        else:
            # Didn't understand, ask again
            self._send_response(
                phone_number=message.phone_number,
                response_type="ask_user_type",
                language=session.language or "hi-IN",
                data={},
            )

    def _handle_language_selection(self, message: InboundMessage, session: Session) -> None:
        """Process language selection."""
        # Auto-detect from voice or let user choose
        if message.text_body:
            lang_map = {
                "hindi": "hi-IN", "english": "en-IN", "tamil": "ta-IN",
                "telugu": "te-IN", "bengali": "bn-IN", "marathi": "mr-IN",
                "gujarati": "gu-IN", "kannada": "kn-IN", "malayalam": "ml-IN",
                "punjabi": "pa-IN",
            }
            selected = lang_map.get(message.text_body.strip().lower())
            if selected:
                self._session_service.set_language(session, selected)
                self._session_service.advance_state(session, ConversationState.COLLECTING_JOB_INFO)
                return

        self._send_response(
            phone_number=message.phone_number,
            response_type="ask_language",
            language="en-IN",
            data={},
        )

    def _handle_job_info(self, message: InboundMessage, session: Session) -> None:
        """Process job information from voice or text."""
        text = None

        if message.message_type == "audio":
            # Process voice message first
            voice_result = self._invoke_voice_processor(message, session)
            if voice_result.get("low_confidence"):
                self._send_response(
                    phone_number=message.phone_number,
                    response_type="low_confidence",
                    language=session.language or "hi-IN",
                    data={},
                )
                return
            text = voice_result.get("text", "")
            # Update language if detected
            detected_lang = voice_result.get("language")
            if detected_lang and not session.language:
                self._session_service.set_language(session, detected_lang)
                session.language = detected_lang
        elif message.text_body:
            text = message.text_body

        if not text:
            return

        # Extract entities
        extraction_result = self._invoke_entity_extractor(text, session)
        extracted_entities = extraction_result.get("extracted_entities", {})

        # Update session with extracted data
        session = self._session_service.advance_state(
            session,
            ConversationState.COLLECTING_JOB_INFO,
            extracted_entities,
        )

        # Check completeness
        is_complete, missing = self._session_service.check_data_completeness(session)

        if is_complete:
            if session.user_type == "worker":
                self._handle_matching(message.phone_number, session)
            else:
                self._handle_job_posting_creation(message.phone_number, session)
        else:
            # Send follow-up question for missing fields
            follow_up = extraction_result.get("follow_up")
            self._send_response(
                phone_number=message.phone_number,
                response_type="follow_up",
                language=session.language or "hi-IN",
                data={"missing_fields": missing, "follow_up_question": follow_up},
            )

    def _handle_matching(self, phone_number: str, session: Session) -> None:
        """Trigger matching and send results."""
        self._session_service.advance_state(session, ConversationState.MATCHING)

        match_result = self._invoke_matcher(session.extracted_data)
        matches = match_result.get("matches", [])

        session = self._session_service.advance_state(
            session,
            ConversationState.VIEWING_MATCHES,
            {"last_matches": matches},
        )

        self._send_response(
            phone_number=phone_number,
            response_type="matches",
            language=session.language or "hi-IN",
            data={"matches": matches},
        )

    def _handle_job_posting_creation(self, phone_number: str, session: Session) -> None:
        """Create a job posting from employer's extracted data."""
        from common.models.job_posting import Availability, JobPosting, Location, SalaryRange
        from common.repositories.job_posting_repository import JobPostingRepository

        data = session.extracted_data
        posting = JobPosting(
            job_id=JobPosting.generate_id(),
            employer_phone=phone_number,
            job_type=data.get("job_type", ""),
            location=Location.from_dict(data.get("location", {})),
            salary=SalaryRange.from_dict(data.get("salary", {})),
            availability=Availability.from_dict(data.get("availability", {})),
            required_skills=data.get("skills", []),
            description=data.get("description"),
            urgency=data.get("urgency", "flexible"),
        )

        job_repo = JobPostingRepository()
        job_repo.create_posting(posting)

        self._session_service.advance_state(session, ConversationState.COMPLETED)
        self._send_response(
            phone_number=phone_number,
            response_type="posting_created",
            language=session.language or "hi-IN",
            data={"job_id": posting.job_id, "posting": posting.to_dynamodb_item()},
        )

    def _handle_match_selection(self, message: InboundMessage, session: Session) -> None:
        """Process worker's selection of a job match."""
        selected_id = None

        if message.message_type == "interactive" and message.interactive_id:
            selected_id = message.interactive_id
        elif message.text_body:
            text = message.text_body.strip()
            if text in ("1", "2", "3"):
                selected_id = f"match_{text}"

        if selected_id and selected_id.startswith("match_"):
            try:
                match_index = int(selected_id.split("_")[1]) - 1
            except (ValueError, IndexError):
                match_index = -1
            matches = session.extracted_data.get("last_matches", [])
            if 0 <= match_index < len(matches):
                selected_match = matches[match_index]
                job_id = selected_match.get("posting", {}).get("job_id")
                if job_id:
                    from services.contact_exchange_service import ContactExchangeService

                    exchange_service = ContactExchangeService()
                    exchange_service.initiate_exchange(
                        worker_phone=message.phone_number,
                        job_id=job_id,
                        worker_session=session,
                    )
                    return

        # Invalid selection
        self._send_response(
            phone_number=message.phone_number,
            response_type="invalid_selection",
            language=session.language or "hi-IN",
            data={},
        )

    def _handle_exchange_confirmation(self, message: InboundMessage, session: Session) -> None:
        """Process employer's confirmation/rejection of contact exchange."""
        confirmed = False

        if message.message_type == "interactive" and message.interactive_id:
            confirmed = message.interactive_id == "confirm_exchange"
        elif message.text_body:
            text = message.text_body.strip().lower()
            confirmed = text in ("yes", "haan", "ha", "ok", "1", "confirm")

        from services.contact_exchange_service import ContactExchangeService

        exchange_service = ContactExchangeService()
        if confirmed:
            exchange_service.confirm_exchange(message.phone_number, session)
        else:
            exchange_service.reject_exchange(message.phone_number, session)

    # === Lambda invocation helpers ===

    def _invoke_lambda(self, function_name: str, payload: dict) -> dict:
        """Invoke a Lambda function synchronously, checking for errors."""
        response = self._lambda.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        payload_bytes = response["Payload"].read()
        if response.get("FunctionError"):
            error_detail = json.loads(payload_bytes)
            raise RuntimeError(
                f"Lambda {function_name} failed: "
                f"{error_detail.get('errorMessage', 'unknown error')}"
            )
        return json.loads(payload_bytes)

    def _invoke_voice_processor(self, message: InboundMessage, session: Session) -> dict:
        """Invoke Voice Processor Lambda synchronously."""
        return self._invoke_lambda(config.VOICE_PROCESSOR_FUNCTION, {
            "media_id": message.media_id,
            "phone_number": message.phone_number,
            "language_hint": session.language,
        })

    def _invoke_entity_extractor(self, text: str, session: Session) -> dict:
        """Invoke Entity Extractor Lambda synchronously."""
        return self._invoke_lambda(config.ENTITY_EXTRACTOR_FUNCTION, {
            "text": text,
            "session": session.to_dynamodb_item(),
            "user_type": session.user_type or "worker",
        })

    def _invoke_matcher(self, worker_data: dict) -> dict:
        """Invoke Matcher Lambda synchronously."""
        return self._invoke_lambda(config.MATCHER_FUNCTION, {
            "worker_data": worker_data,
            "limit": config.MAX_MATCHES_RETURNED,
        })

    def _send_response(self, phone_number: str, response_type: str, language: str, data: dict) -> None:
        """Invoke Response Generator Lambda synchronously."""
        self._invoke_lambda(config.RESPONSE_GENERATOR_FUNCTION, {
            "phone_number": phone_number,
            "response_type": response_type,
            "language": language,
            "data": data,
        })

    def _send_error_response(self, phone_number: str, language: str) -> None:
        """Send a generic error response."""
        self._send_response(phone_number, "error", language, {})
