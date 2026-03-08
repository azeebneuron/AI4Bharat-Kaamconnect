class KaamConnectError(Exception):
    """Base exception for all KaamConnect errors."""


# Session errors
class SessionExpiredError(KaamConnectError):
    """Session has expired (inactive for 24+ hours)."""


class SessionNotFoundError(KaamConnectError):
    """No active session found for the given phone number."""


# Transcription errors
class TranscriptionError(KaamConnectError):
    """Error during voice transcription."""


class LowConfidenceError(TranscriptionError):
    """Transcription confidence below 90% threshold."""


class UnsupportedLanguageError(TranscriptionError):
    """Voice message is in an unsupported language."""


# Entity extraction errors
class ExtractionError(KaamConnectError):
    """Error during entity extraction from text."""


class IncompleteDataError(ExtractionError):
    """Required fields are missing from extracted data."""


class AmbiguousInputError(ExtractionError):
    """Input is ambiguous and requires clarification."""


# Matching errors
class MatchingError(KaamConnectError):
    """Error during job matching."""


class NoMatchesError(MatchingError):
    """No job postings match above the minimum threshold."""


# WhatsApp / EUMS errors
class WhatsAppError(KaamConnectError):
    """Error communicating with WhatsApp via EUMS."""


class MediaDownloadError(WhatsAppError):
    """Failed to download media (voice file) from WhatsApp."""


# Rate limiting
class RateLimitError(KaamConnectError):
    """User has exceeded the rate limit."""
