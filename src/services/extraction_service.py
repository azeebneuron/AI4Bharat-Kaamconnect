"""Entity extraction using Amazon Bedrock Claude Haiku.

Extracts structured job information (type, location, salary, skills,
availability) from natural language text in 10+ Indian languages.
"""

import json
import re
from pathlib import Path
from typing import Optional

from common.clients.bedrock_client import BedrockClient
from common.exceptions import ExtractionError
from common.logger import get_logger, log_context

logger = get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


class ExtractionService:
    """Extracts structured job entities from natural language text."""

    def __init__(self, bedrock_client: Optional[BedrockClient] = None):
        self._bedrock = bedrock_client or BedrockClient()
        self._prompt_template = self._load_prompt("entity_extraction.txt")

    def extract_entities(
        self,
        text: str,
        session_data: dict,
        user_type: str = "worker",
    ) -> dict:
        """Extract job entities from text using Bedrock Claude.

        Returns: {
            "extracted_entities": dict,
            "follow_up": str or None,
            "confidence": float,
        }
        """
        if not text.strip():
            return {"extracted_entities": {}, "follow_up": None, "confidence": 0.0}

        # Validate inputs to prevent injection
        if user_type not in ("worker", "employer"):
            user_type = "worker"
        intent = "find work" if user_type == "worker" else "hire workers"
        existing_data = session_data.get("extracted_data", {})
        language = session_data.get("language", "hindi")
        if language not in ("hindi", "english", "tamil", "telugu", "bengali",
                            "marathi", "gujarati", "kannada", "malayalam", "punjabi",
                            "hi-IN", "en-IN", "ta-IN", "te-IN", "bn-IN",
                            "mr-IN", "gu-IN", "kn-IN", "ml-IN", "pa-IN"):
            language = "hindi"

        system_prompt = self._prompt_template.format(
            user_type=user_type,
            intent=intent,
            language=language,
            existing_data=json.dumps(existing_data, ensure_ascii=False, default=str),
        )

        try:
            response_text = self._bedrock.invoke_claude(
                system_prompt=system_prompt,
                user_message=text,
                max_tokens=512,
                temperature=0.1,
            )

            parsed = self._parse_json_response(response_text)

            # Merge with existing data
            extracted = parsed.get("extracted_entities", {})
            merged = self._merge_entities(existing_data, extracted)

            return {
                "extracted_entities": merged,
                "follow_up": parsed.get("follow_up"),
                "confidence": parsed.get("confidence", 0.5),
            }

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse Bedrock response as JSON", extra=log_context(error=str(e)))
            return {"extracted_entities": {}, "follow_up": None, "confidence": 0.0}
        except Exception as e:
            raise ExtractionError(f"Entity extraction failed: {e}") from e

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from Bedrock response, handling markdown code fences."""
        # Try to find JSON block within code fences
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1).strip())

        # Try parsing the entire response as JSON
        text = text.strip()
        if text.startswith("{"):
            return json.loads(text)

        # Try to find first complete JSON object by scanning for balanced braces
        start = text.find("{")
        if start != -1:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError("No JSON found in response", text, 0)

    def _merge_entities(self, existing: dict, new: dict) -> dict:
        """Smart merge: new non-null values fill gaps without overwriting."""
        result = {**existing}
        for key, value in new.items():
            if value is None:
                continue
            if key not in result or result[key] is None:
                result[key] = value
            elif isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge_entities(result[key], value)
        return result

    def _load_prompt(self, filename: str) -> str:
        """Load a prompt template from the prompts directory."""
        prompt_path = PROMPTS_DIR / filename
        if prompt_path.exists():
            return prompt_path.read_text()
        # Fallback inline prompt if file doesn't exist yet
        return self._default_prompt()

    def _default_prompt(self) -> str:
        return """You are KaamConnect, a job matching assistant for India's blue-collar workers.
Extract structured job information from the user's message.

The user is a {user_type} looking to {intent}.
Their preferred language is {language}.
Previously collected information: {existing_data}

Extract these entities from the message. Return ONLY valid JSON, no other text.
- job_type: one of (plumber, electrician, maid, cook, driver, carpenter, painter, mason, security_guard, delivery, warehouse, factory, tailor, gardener, ac_mechanic, welder, helper, cleaner, watchman, peon)
- location: object with area (string or null), city (string), pincode (string or null)
- salary: object with min (number or null), max (number or null), period ("daily" or "monthly")
- availability: object with days (list of day names), hours ("morning"|"afternoon"|"evening"|"night"|"flexible")
- skills: list of relevant skill strings
- experience_years: number or null
- urgency: "immediate" | "within_week" | "flexible"

Important rules:
- Understand Hindi, Hinglish, and regional languages natively
- "plumbing ka kaam" / "panni fitting" = job_type: "plumber"
- "Koramangala mein" = location.area: "Koramangala", location.city: "Bangalore"
- "500 rupay daily" = salary.min: 500, salary.max: 500, salary.period: "daily"
- Only include fields you are confident about. Set uncertain fields to null.
- If critical info is missing, generate a follow-up question in {language}.

Return format:
{{
  "extracted_entities": {{ ... }},
  "follow_up": "natural language question or null",
  "confidence": 0.0 to 1.0
}}"""
