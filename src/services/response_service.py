"""WhatsApp response generation and sending.

Generates contextual, multilingual responses using templates
and Bedrock for dynamic content, then sends via EUMS.
"""

import json
from pathlib import Path
from typing import Optional

from common.clients.bedrock_client import BedrockClient
from common.clients.eums_client import EUMSClient
from common.logger import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Multilingual static messages
MESSAGES = {
    "welcome": {
        "hi-IN": "🙏 नमस्ते! KaamConnect में आपका स्वागत है।\n\nहम आपको नौकरी ढूंढने या कामगार ढूंढने में मदद करते हैं।\n\nकृपया बताएं - आप कौन हैं?",
        "en-IN": "🙏 Welcome to KaamConnect!\n\nWe help you find jobs or hire workers.\n\nPlease tell us - who are you?",
        "ta-IN": "🙏 KaamConnect-க்கு வரவேற்கிறோம்!\n\nவேலை கண்டுபிடிக்க அல்லது தொழிலாளர்களை பணியமர்த்த நாங்கள் உதவுகிறோம்.",
        "te-IN": "🙏 KaamConnect కి స్వాగతం!\n\nమీకు ఉద్యోగం కనుగొనడంలో లేదా కార్మికులను నియమించడంలో సహాయం చేస్తాము.",
        "bn-IN": "🙏 KaamConnect-এ স্বাগতম!\n\nআমরা আপনাকে চাকরি খুঁজতে বা কর্মী নিয়োগে সাহায্য করি.",
    },
    "ask_user_type": {
        "hi-IN": "आप कामगार हैं या नियोक्ता?\n\n1️⃣ कामगार (काम ढूंढ रहे हैं)\n2️⃣ नियोक्ता (कामगार ढूंढ रहे हैं)",
        "en-IN": "Are you a worker or employer?\n\n1️⃣ Worker (looking for work)\n2️⃣ Employer (looking to hire)",
    },
    "ask_job_details_worker": {
        "hi-IN": "बढ़िया! आप कौनसा काम करते हैं और कहाँ काम चाहिए?\n\n🎤 आप voice message भेज सकते हैं या type कर सकते हैं।\n\nउदाहरण: \"मैं plumber हूँ, Koramangala में काम चाहिए, 600 रुपये daily\"",
        "en-IN": "Great! What work do you do and where do you need a job?\n\n🎤 You can send a voice message or type.\n\nExample: \"I'm a plumber, need work in Koramangala, 600 rupees daily\"",
    },
    "ask_job_details_employer": {
        "hi-IN": "बढ़िया! आपको कौनसा कामगार चाहिए?\n\n🎤 Voice message भेजें या type करें।\n\nउदाहरण: \"मुझे Indiranagar में एक maid चाहिए, 8000 रुपये monthly\"",
        "en-IN": "Great! What kind of worker do you need?\n\n🎤 Send a voice message or type.\n\nExample: \"I need a maid in Indiranagar, 8000 rupees monthly\"",
    },
    "low_confidence": {
        "hi-IN": "माफ़ करें, आपका message ठीक से समझ नहीं आया। कृपया दोबारा भेजें - शांत जगह से बोलें। 🎤",
        "en-IN": "Sorry, we couldn't understand your message clearly. Please try again - speak from a quiet place. 🎤",
    },
    "no_matches": {
        "hi-IN": "अभी आपकी ज़रूरतों के अनुसार कोई काम उपलब्ध नहीं है। जैसे ही कोई नया काम आएगा, हम आपको बताएंगे! 🔔",
        "en-IN": "No matching jobs found right now. We'll notify you when something comes up! 🔔",
    },
    "posting_created": {
        "hi-IN": "✅ आपकी job posting बन गई है!\n\nJob ID: {job_id}\n\nजैसे ही कोई कामगार मिलेगा, हम आपसे संपर्क करेंगे।",
        "en-IN": "✅ Your job posting has been created!\n\nJob ID: {job_id}\n\nWe'll contact you when a worker matches.",
    },
    "contact_shared": {
        "hi-IN": "🎉 बधाई हो! मैच मिल गया!\n\n📞 संपर्क नंबर: {contact_number}\n\nसीधे बात करें और काम तय करें। KaamConnect आपकी सेवा में! 🙏",
        "en-IN": "🎉 Congratulations! Match found!\n\n📞 Contact number: {contact_number}\n\nCall directly to discuss the job. KaamConnect at your service! 🙏",
    },
    "error": {
        "hi-IN": "कुछ गड़बड़ हो गई। कृपया थोड़ी देर बाद फिर कोशिश करें। 🙏",
        "en-IN": "Something went wrong. Please try again in a moment. 🙏",
    },
}


class ResponseService:
    """Generates and sends WhatsApp responses."""

    def __init__(
        self,
        eums_client: Optional[EUMSClient] = None,
        bedrock_client: Optional[BedrockClient] = None,
    ):
        self._eums = eums_client or EUMSClient()
        self._bedrock = bedrock_client or BedrockClient()

    def send_response(
        self,
        phone_number: str,
        response_type: str,
        language: str = "hi-IN",
        data: Optional[dict] = None,
    ) -> None:
        """Send a response based on type."""
        data = data or {}

        handler_map = {
            "welcome": self._send_welcome,
            "ask_user_type": self._send_user_type_question,
            "ask_language": self._send_language_selection,
            "ask_job_details": self._send_job_details_prompt,
            "follow_up": self._send_follow_up,
            "matches": self._send_match_results,
            "no_matches": self._send_no_matches,
            "posting_created": self._send_posting_confirmation,
            "contact_exchange": self._send_contact_exchange,
            "contact_shared": self._send_contact_shared,
            "confirm_exchange": self._send_exchange_confirmation_request,
            "low_confidence": self._send_low_confidence,
            "invalid_selection": self._send_invalid_selection,
            "please_wait": self._send_please_wait,
            "error": self._send_error,
        }

        handler = handler_map.get(response_type, self._send_error)
        handler(phone_number, language, data)

    def _send_welcome(self, phone_number: str, language: str, data: dict) -> None:
        """Send welcome message with user type buttons."""
        text = self._get_message("welcome", language)
        self._eums.send_text_message(phone_number, text)

        # Send interactive buttons for user type
        self._eums.send_interactive_message(phone_number, {
            "type": "button",
            "body": {"text": self._get_message("ask_user_type", language)},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "worker", "title": "🔧 Worker / कामगार"}},
                    {"type": "reply", "reply": {"id": "employer", "title": "🏢 Employer / नियोक्ता"}},
                ]
            },
        })

    def _send_language_selection(self, phone_number: str, language: str, data: dict) -> None:
        """Send language selection prompt."""
        text = (
            "कृपया अपनी भाषा चुनें / Please choose your language:\n\n"
            "1. Hindi\n2. English\n3. Tamil\n4. Telugu\n5. Bengali\n"
            "6. Marathi\n7. Gujarati\n8. Kannada\n9. Malayalam\n10. Punjabi"
        )
        self._eums.send_text_message(phone_number, text)

    def _send_please_wait(self, phone_number: str, language: str, data: dict) -> None:
        """Ask user to wait while processing."""
        if language.startswith("hi"):
            text = "कृपया रुकें, हम आपके लिए काम ढूंढ रहे हैं... ⏳"
        else:
            text = "Please wait, we're finding jobs for you... ⏳"
        self._eums.send_text_message(phone_number, text)

    def _send_user_type_question(self, phone_number: str, language: str, data: dict) -> None:
        self._eums.send_interactive_message(phone_number, {
            "type": "button",
            "body": {"text": self._get_message("ask_user_type", language)},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "worker", "title": "🔧 Worker / कामगार"}},
                    {"type": "reply", "reply": {"id": "employer", "title": "🏢 Employer / नियोक्ता"}},
                ]
            },
        })

    def _send_job_details_prompt(self, phone_number: str, language: str, data: dict) -> None:
        user_type = data.get("user_type", "worker")
        key = f"ask_job_details_{user_type}"
        text = self._get_message(key, language)
        self._eums.send_text_message(phone_number, text)

    def _send_follow_up(self, phone_number: str, language: str, data: dict) -> None:
        """Send follow-up question for missing information."""
        follow_up = data.get("follow_up_question")
        if follow_up:
            self._eums.send_text_message(phone_number, follow_up)
        else:
            # Generate follow-up from missing fields
            missing = data.get("missing_fields", [])
            question = self._generate_follow_up(missing, language)
            self._eums.send_text_message(phone_number, question)

    def _send_match_results(self, phone_number: str, language: str, data: dict) -> None:
        """Send job match results with interactive selection."""
        matches = data.get("matches", [])
        if not matches:
            self._send_no_matches(phone_number, language, data)
            return

        # Build match summaries
        summaries = []
        rows = []
        for i, match in enumerate(matches, 1):
            posting = match.get("posting", {})
            score_pct = int(match.get("score", 0) * 100)
            location = posting.get("location", {})
            salary = posting.get("salary", {})

            area = location.get("area") or location.get("city", "")
            sal_str = ""
            if salary.get("min_amount"):
                sal_str = f"₹{salary['min_amount']}"
                if salary.get("max_amount") and salary["max_amount"] != salary["min_amount"]:
                    sal_str += f"-{salary['max_amount']}"
                sal_str += f"/{salary.get('period', 'daily')}"

            summary = f"{i}. {posting.get('job_type', 'Job')} - {area}"
            if sal_str:
                summary += f" - {sal_str}"
            summary += f" ({score_pct}% match)"
            summaries.append(summary)

            rows.append({
                "id": f"match_{i}",
                "title": f"{posting.get('job_type', 'Job')} in {area}",
                "description": f"{sal_str} | {score_pct}% match" if sal_str else f"{score_pct}% match",
            })

        # Send text summary
        text = "\n".join(summaries)
        header = "🎯 आपके लिए मिलान:" if language.startswith("hi") else "🎯 Matches for you:"
        self._eums.send_text_message(phone_number, f"{header}\n\n{text}")

        # Send interactive list for selection
        select_text = "कौनसा काम पसंद है? नीचे चुनें:" if language.startswith("hi") else "Which job interests you? Select below:"
        self._eums.send_interactive_message(phone_number, {
            "type": "list",
            "body": {"text": select_text},
            "action": {
                "button": "View Jobs / काम देखें",
                "sections": [{"title": "Available Jobs", "rows": rows}],
            },
        })

    def _send_no_matches(self, phone_number: str, language: str, data: dict) -> None:
        text = self._get_message("no_matches", language)
        self._eums.send_text_message(phone_number, text)

    def _send_posting_confirmation(self, phone_number: str, language: str, data: dict) -> None:
        text = self._get_message("posting_created", language).format(
            job_id=data.get("job_id", "N/A")
        )
        self._eums.send_text_message(phone_number, text)

    def _send_contact_exchange(self, phone_number: str, language: str, data: dict) -> None:
        pass  # Handled by contact_exchange_service

    def _send_contact_shared(self, phone_number: str, language: str, data: dict) -> None:
        text = self._get_message("contact_shared", language).format(
            contact_number=data.get("contact_number", "N/A")
        )
        self._eums.send_text_message(phone_number, text)

    def _send_exchange_confirmation_request(self, phone_number: str, language: str, data: dict) -> None:
        """Ask employer to confirm contact exchange."""
        worker_info = data.get("worker_info", {})
        job_type = worker_info.get("job_type", "worker")

        if language.startswith("hi"):
            text = f"एक {job_type} आपकी job posting में interested है। क्या आप contact details share करना चाहेंगे?"
        else:
            text = f"A {job_type} is interested in your job posting. Would you like to share contact details?"

        self._eums.send_interactive_message(phone_number, {
            "type": "button",
            "body": {"text": text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "confirm_exchange", "title": "✅ Yes / हाँ"}},
                    {"type": "reply", "reply": {"id": "reject_exchange", "title": "❌ No / नहीं"}},
                ]
            },
        })

    def _send_low_confidence(self, phone_number: str, language: str, data: dict) -> None:
        text = self._get_message("low_confidence", language)
        self._eums.send_text_message(phone_number, text)

    def _send_invalid_selection(self, phone_number: str, language: str, data: dict) -> None:
        if language.startswith("hi"):
            text = "कृपया सही विकल्प चुनें।"
        else:
            text = "Please select a valid option."
        self._eums.send_text_message(phone_number, text)

    def _send_error(self, phone_number: str, language: str, data: dict) -> None:
        text = self._get_message("error", language)
        self._eums.send_text_message(phone_number, text)

    def _get_message(self, key: str, language: str) -> str:
        """Get a static message in the given language, fallback to Hindi then English."""
        messages = MESSAGES.get(key, {})
        return messages.get(language, messages.get("hi-IN", messages.get("en-IN", "")))

    def _generate_follow_up(self, missing_fields: list[str], language: str) -> str:
        """Generate a follow-up question for missing fields."""
        field_questions = {
            "job_type": {"hi-IN": "आप कौनसा काम करते हैं?", "en-IN": "What type of work do you do?"},
            "location": {"hi-IN": "आप कहाँ काम चाहते हैं? (शहर और इलाका बताएं)", "en-IN": "Where do you want to work? (city and area)"},
            "salary": {"hi-IN": "आपकी salary expectation क्या है? (daily या monthly)", "en-IN": "What's your salary expectation? (daily or monthly)"},
            "availability": {"hi-IN": "आप कब काम कर सकते हैं? (सुबह/दोपहर/शाम)", "en-IN": "When can you work? (morning/afternoon/evening)"},
            "skills": {"hi-IN": "आपकी speciality क्या है?", "en-IN": "What are your special skills?"},
        }

        questions = []
        for field in missing_fields[:2]:  # Ask max 2 questions at a time
            q = field_questions.get(field, {})
            questions.append(q.get(language, q.get("hi-IN", q.get("en-IN", ""))))

        return "\n\n".join(q for q in questions if q)
