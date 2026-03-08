"""Web chat conversation service.

Adapts the existing conversation state machine for web interface.
Calls services directly instead of cross-Lambda invocation.
Returns response dicts instead of sending via EUMS/WhatsApp.
"""

import base64
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from common import config
from common.clients.s3_client import S3Client
from common.clients.transcribe_client import TranscribeClient
from common.exceptions import LowConfidenceError
from common.logger import get_logger, log_context
from common.models.session import ConversationState, Session
from services.extraction_service import ExtractionService
from services.matching_service import MatchingService
from services.session_service import SessionService

logger = get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.50

MESSAGES = {
    "welcome": {
        "hi-IN": "नमस्ते! KaamConnect में आपका स्वागत है।\n\nहम आपको नौकरी ढूंढने या कामगार ढूंढने में मदद करते हैं।\n\nकृपया बताएं - आप कामगार हैं या नियोक्ता?",
        "en-IN": "Welcome to KaamConnect!\n\nWe help you find jobs or hire workers.\n\nAre you a Worker or Employer?",
    },
    "ask_user_type": {
        "hi-IN": "आप कामगार हैं या नियोक्ता?\n\n1. कामगार (काम ढूंढ रहे हैं)\n2. नियोक्ता (कामगार ढूंढ रहे हैं)",
        "en-IN": "Are you a worker or employer?\n\n1. Worker (looking for work)\n2. Employer (looking to hire)",
    },
    "ask_job_details_worker": {
        "hi-IN": "बढ़िया! आप कौनसा काम करते हैं और कहाँ काम चाहिए?\n\nVoice message भेज सकते हैं या type कर सकते हैं।",
        "en-IN": "Great! What work do you do and where do you need a job?\n\nYou can send a voice message or type.",
    },
    "ask_job_details_employer": {
        "hi-IN": "बढ़िया! आपको कौनसा कामगार चाहिए?\n\nVoice message भेजें या type करें।",
        "en-IN": "Great! What kind of worker do you need?\n\nSend a voice message or type.",
    },
    "low_confidence": {
        "hi-IN": "माफ़ करें, आपका message ठीक से समझ नहीं आया। कृपया दोबारा भेजें।",
        "en-IN": "Sorry, couldn't understand clearly. Please try again.",
    },
    "no_matches": {
        "hi-IN": "अभी आपकी ज़रूरतों के अनुसार कोई काम उपलब्ध नहीं है।",
        "en-IN": "No matching jobs found right now.",
    },
    "posting_created": {
        "hi-IN": "आपकी job posting बन गई है! Job ID: {job_id}",
        "en-IN": "Your job posting has been created! Job ID: {job_id}",
    },
    "error": {
        "hi-IN": "कुछ गड़बड़ हो गई। कृपया दोबारा कोशिश करें।",
        "en-IN": "Something went wrong. Please try again.",
    },
    "please_wait": {
        "hi-IN": "कृपया रुकें, हम आपके लिए काम ढूंढ रहे हैं...",
        "en-IN": "Please wait, finding jobs for you...",
    },
}


class WebChatService:
    """Handles web chat conversation flow, calling services directly."""

    def __init__(
        self,
        session_service: Optional[SessionService] = None,
        extraction_service: Optional[ExtractionService] = None,
        matching_service: Optional[MatchingService] = None,
        s3_client: Optional[S3Client] = None,
        transcribe_client: Optional[TranscribeClient] = None,
    ):
        self._session_service = session_service or SessionService()
        self._extraction = extraction_service or ExtractionService()
        self._matching = matching_service or MatchingService()
        self._s3 = s3_client or S3Client()
        self._transcribe = transcribe_client or TranscribeClient()

    def process_message(
        self,
        session_id: Optional[str] = None,
        text: Optional[str] = None,
        audio_base64: Optional[str] = None,
        language: Optional[str] = None,
    ) -> dict:
        """Process a web chat message and return response.

        Args:
            session_id: Existing session ID or None for new session.
            text: Text message from user.
            audio_base64: Base64-encoded audio data.
            language: Language hint (e.g., "hi-IN").

        Returns: {
            "session_id": str,
            "response_text": str,
            "conversation_state": str,
            "buttons": [...] or None,
            "matches": [...] or None,
            "transcribed_text": str or None,
        }
        """
        # Use a stable web_id as the phone_number key for DynamoDB lookup.
        # The web_id is persisted in the browser and sent back on each request.
        self._current_web_id = session_id or uuid4().hex[:16]
        phone_key = f"web_{self._current_web_id}"

        session = self._session_service.get_or_create_session(phone_key)

        if language and not session.language:
            self._session_service.set_language(session, language)
            session.language = language

        state = session.conversation_state
        try:
            if state == ConversationState.NEW:
                return self._handle_new_user(session)
            elif state == ConversationState.AWAITING_USER_TYPE:
                return self._handle_user_type(session, text)
            elif state in (
                ConversationState.COLLECTING_JOB_INFO,
                ConversationState.AWAITING_CONFIRMATION,
            ):
                return self._handle_job_info(session, text, audio_base64, language)
            elif state == ConversationState.MATCHING:
                return self._make_response(session, "please_wait")
            elif state == ConversationState.VIEWING_MATCHES:
                return self._handle_match_selection(session, text)
            elif state == ConversationState.COMPLETED:
                return self._handle_new_user(session)
            else:
                return self._handle_job_info(session, text, audio_base64, language)
        except Exception as e:
            logger.exception(
                "Error processing web message", extra=log_context(error=str(e))
            )
            return self._make_response(session, "error")

    def _handle_new_user(self, session: Session) -> dict:
        self._session_service.advance_state(
            session, ConversationState.AWAITING_USER_TYPE
        )
        return self._make_response(
            session,
            "welcome",
            buttons=[
                {"id": "worker", "label": "Worker / कामगार"},
                {"id": "employer", "label": "Employer / नियोक्ता"},
            ],
        )

    def _handle_user_type(self, session: Session, text: Optional[str]) -> dict:
        user_type = None
        if text:
            t = text.strip().lower()
            if t in ("worker", "kaamgar", "kaam", "1", "majdoor"):
                user_type = "worker"
            elif t in ("employer", "malik", "2", "niyokta"):
                user_type = "employer"

        if user_type:
            self._session_service.set_user_type(session, user_type)
            session.user_type = user_type
            self._session_service.advance_state(
                session, ConversationState.COLLECTING_JOB_INFO
            )
            key = f"ask_job_details_{user_type}"
            return self._make_response(session, key)
        else:
            return self._make_response(
                session,
                "ask_user_type",
                buttons=[
                    {"id": "worker", "label": "Worker / कामगार"},
                    {"id": "employer", "label": "Employer / नियोक्ता"},
                ],
            )

    def _handle_job_info(
        self,
        session: Session,
        text: Optional[str],
        audio_base64: Optional[str],
        language: Optional[str],
    ) -> dict:
        transcribed_text = None

        if audio_base64:
            try:
                result = self._transcribe_audio(audio_base64, session, language)
                text = result["text"]
                transcribed_text = text
                detected_lang = result.get("language")
                if detected_lang and not session.language:
                    self._session_service.set_language(session, detected_lang)
                    session.language = detected_lang
            except LowConfidenceError:
                return self._make_response(
                    session, "low_confidence", transcribed_text=transcribed_text
                )

        if not text:
            key = f"ask_job_details_{session.user_type or 'worker'}"
            return self._make_response(session, key)

        # Extract entities directly
        extraction_result = self._extraction.extract_entities(
            text=text,
            session_data=session.to_dynamodb_item(),
            user_type=session.user_type or "worker",
        )
        extracted_entities = extraction_result.get("extracted_entities", {})
        # Convert any floats to Decimal for DynamoDB
        extracted_entities = self._floats_to_decimals(extracted_entities)

        session = self._session_service.advance_state(
            session,
            ConversationState.COLLECTING_JOB_INFO,
            extracted_entities,
        )

        is_complete, missing = self._session_service.check_data_completeness(session)

        if is_complete:
            if session.user_type == "worker":
                return self._handle_matching(session, transcribed_text)
            else:
                return self._handle_posting_creation(session, transcribed_text)
        else:
            follow_up = extraction_result.get("follow_up")
            if not follow_up:
                follow_up = self._generate_follow_up(
                    missing, session.language or "hi-IN"
                )
            return self._make_response(
                session,
                None,
                custom_text=follow_up,
                transcribed_text=transcribed_text,
            )

    def _handle_matching(
        self, session: Session, transcribed_text: Optional[str] = None
    ) -> dict:
        self._session_service.advance_state(session, ConversationState.MATCHING)

        matches = self._matching.find_matches(
            worker_data=session.extracted_data,
            limit=config.MAX_MATCHES_RETURNED,
        )

        serialized = []
        for match in matches:
            serialized.append(
                {
                    "posting": match["posting"].to_dynamodb_item(),
                    "score": float(match["score"]),
                    "breakdown": {k: float(v) for k, v in match["breakdown"].items()},
                }
            )

        # DynamoDB requires Decimal, not float — convert for storage
        dynamo_safe = self._floats_to_decimals(serialized)
        session = self._session_service.advance_state(
            session,
            ConversationState.VIEWING_MATCHES,
            {"last_matches": dynamo_safe},
        )

        if not serialized:
            return self._make_response(
                session, "no_matches", transcribed_text=transcribed_text
            )

        lang = session.language or "hi-IN"
        header = (
            "आपके लिए मिलान:"
            if lang.startswith("hi")
            else "Matches for you:"
        )
        lines = [header, ""]
        buttons = []
        for i, m in enumerate(serialized, 1):
            posting = m["posting"]
            score_pct = int(m["score"] * 100)
            loc = posting.get("location", {})
            sal = posting.get("salary", {})
            area = loc.get("area") or loc.get("city", "")
            sal_str = ""
            if sal.get("min_amount"):
                sal_str = f"₹{sal['min_amount']}"
                if sal.get("max_amount") and sal["max_amount"] != sal["min_amount"]:
                    sal_str += f"-{sal['max_amount']}"
                sal_str += f"/{sal.get('period', 'daily')}"

            line = f"{i}. {posting.get('job_type', 'Job')} - {area}"
            if sal_str:
                line += f" - {sal_str}"
            line += f" ({score_pct}% match)"
            lines.append(line)
            buttons.append(
                {
                    "id": f"match_{i}",
                    "label": f"{posting.get('job_type', 'Job')} in {area}",
                }
            )

        select_msg = (
            "\n\nकौनसा काम पसंद है? नंबर भेजें:"
            if lang.startswith("hi")
            else "\n\nWhich job? Send the number:"
        )
        lines.append(select_msg)

        return self._make_response(
            session,
            None,
            custom_text="\n".join(lines),
            buttons=buttons,
            matches=serialized,
            transcribed_text=transcribed_text,
        )

    def _handle_posting_creation(
        self, session: Session, transcribed_text: Optional[str] = None
    ) -> dict:
        from common.models.job_posting import (
            Availability,
            JobPosting,
            Location,
            SalaryRange,
        )
        from common.repositories.job_posting_repository import JobPostingRepository

        data = session.extracted_data
        posting = JobPosting(
            job_id=JobPosting.generate_id(),
            employer_phone=session.phone_number,
            job_type=data.get("job_type", ""),
            location=Location.from_dict(data.get("location", {})),
            salary=SalaryRange.from_dict(data.get("salary", {})),
            availability=Availability.from_dict(data.get("availability", {})),
            required_skills=data.get("skills", []),
            urgency=data.get("urgency", "flexible"),
        )

        repo = JobPostingRepository()
        repo.create_posting(posting)

        self._session_service.advance_state(session, ConversationState.COMPLETED)

        lang = session.language or "hi-IN"
        text = self._get_message("posting_created", lang).format(
            job_id=posting.job_id
        )
        return self._make_response(
            session, None, custom_text=text, transcribed_text=transcribed_text
        )

    def _handle_match_selection(self, session: Session, text: Optional[str]) -> dict:
        if not text:
            lang = session.language or "hi-IN"
            msg = (
                "कृपया नंबर चुनें (1, 2, या 3)।"
                if lang.startswith("hi")
                else "Please select a job number (1, 2, or 3)."
            )
            return self._make_response(session, None, custom_text=msg)

        t = text.strip()
        match_index = -1
        if t in ("1", "2", "3"):
            match_index = int(t) - 1
        elif t.startswith("match_"):
            try:
                match_index = int(t.split("_")[1]) - 1
            except (ValueError, IndexError):
                pass

        matches = session.extracted_data.get("last_matches", [])
        if 0 <= match_index < len(matches):
            selected = matches[match_index]
            posting = selected.get("posting", {})
            employer_phone = posting.get("employer_phone", "N/A")
            job_type = posting.get("job_type", "job")
            loc = posting.get("location", {})
            area = loc.get("area") or loc.get("city", "")

            self._session_service.advance_state(session, ConversationState.COMPLETED)

            lang = session.language or "hi-IN"
            if lang.startswith("hi"):
                msg = f"बधाई हो! आपने {job_type} - {area} चुना।\n\nनियोक्ता का नंबर: {employer_phone}\n\nसीधे बात करें!"
            else:
                msg = f"Great choice! You selected {job_type} - {area}.\n\nEmployer contact: {employer_phone}\n\nCall them directly!"

            return self._make_response(session, None, custom_text=msg)
        else:
            lang = session.language or "hi-IN"
            msg = (
                "कृपया सही नंबर चुनें (1, 2, या 3)।"
                if lang.startswith("hi")
                else "Please select a valid number (1, 2, or 3)."
            )
            return self._make_response(session, None, custom_text=msg)

    def _transcribe_audio(
        self,
        audio_base64: str,
        session: Session,
        language: Optional[str],
    ) -> dict:
        """Transcribe base64 audio using S3 + Transcribe pipeline."""
        audio_bytes = base64.b64decode(audio_base64)
        s3_key = self._s3.generate_voice_key(session.phone_number)

        self._s3.upload_voice_file(s3_key, audio_bytes, content_type="audio/webm")
        s3_uri = self._s3.get_s3_uri(s3_key)

        job_name = None
        try:
            job_name = self._transcribe.start_transcription(
                s3_uri=s3_uri,
                language_code=language or session.language,
                media_format="webm",
            )
            result = self._transcribe.get_transcription_result(job_name)

            if result["confidence"] < CONFIDENCE_THRESHOLD:
                raise LowConfidenceError(
                    f"Confidence {result['confidence']:.2f} below threshold"
                )
            return result
        finally:
            self._s3.delete_voice_file(s3_key)
            if job_name:
                self._transcribe.cleanup_job(job_name)

    def _make_response(
        self,
        session: Session,
        message_key: Optional[str],
        buttons: Optional[list] = None,
        matches: Optional[list] = None,
        custom_text: Optional[str] = None,
        transcribed_text: Optional[str] = None,
    ) -> dict:
        lang = session.language or "hi-IN"
        text = custom_text or (
            self._get_message(message_key, lang) if message_key else ""
        )

        return {
            "session_id": self._current_web_id,
            "response_text": text,
            "conversation_state": str(session.conversation_state),
            "buttons": buttons,
            "matches": matches,
            "transcribed_text": transcribed_text,
            "language": lang,
        }

    @staticmethod
    def _floats_to_decimals(obj):
        """Recursively convert float values to Decimal for DynamoDB compatibility."""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: WebChatService._floats_to_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [WebChatService._floats_to_decimals(v) for v in obj]
        return obj

    def _get_message(self, key: str, language: str) -> str:
        messages = MESSAGES.get(key, {})
        return messages.get(language, messages.get("hi-IN", messages.get("en-IN", "")))

    def _generate_follow_up(self, missing_fields: list[str], language: str) -> str:
        field_questions = {
            "job_type": {
                "hi-IN": "आप कौनसा काम करते हैं?",
                "en-IN": "What type of work do you do?",
            },
            "location": {
                "hi-IN": "आप कहाँ काम चाहते हैं? (शहर और इलाका)",
                "en-IN": "Where do you want to work? (city and area)",
            },
            "salary": {
                "hi-IN": "आपकी salary expectation क्या है?",
                "en-IN": "What's your salary expectation?",
            },
        }
        questions = []
        for field in missing_fields[:2]:
            q = field_questions.get(field, {})
            questions.append(q.get(language, q.get("hi-IN", q.get("en-IN", ""))))
        return "\n\n".join(q for q in questions if q)
