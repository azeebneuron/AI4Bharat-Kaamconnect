import os


# AWS Regions
REGION = os.environ.get("AWS_REGION", "ap-south-1")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-south-1")

# Bedrock
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "apac.amazon.nova-micro-v1:0")

# DynamoDB table names
SESSIONS_TABLE = os.environ.get("SESSIONS_TABLE", "kaamconnect-sessions")
JOB_POSTINGS_TABLE = os.environ.get("JOB_POSTINGS_TABLE", "kaamconnect-job-postings")
USER_PROFILES_TABLE = os.environ.get("USER_PROFILES_TABLE", "kaamconnect-user-profiles")

# S3
S3_VOICE_BUCKET = os.environ.get("S3_VOICE_BUCKET", "kaamconnect-voice-files")

# SNS
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

# Lambda function names (for cross-invocation)
VOICE_PROCESSOR_FUNCTION = os.environ.get("VOICE_PROCESSOR_FUNCTION", "kaamconnect-voice-processor")
ENTITY_EXTRACTOR_FUNCTION = os.environ.get("ENTITY_EXTRACTOR_FUNCTION", "kaamconnect-entity-extractor")
MATCHER_FUNCTION = os.environ.get("MATCHER_FUNCTION", "kaamconnect-matcher")
RESPONSE_GENERATOR_FUNCTION = os.environ.get("RESPONSE_GENERATOR_FUNCTION", "kaamconnect-response-generator")

# EUMS (WhatsApp) — runs in us-east-1
EUMS_PHONE_NUMBER_ARN = os.environ.get("EUMS_PHONE_NUMBER_ARN", "")
EUMS_REGION = os.environ.get("EUMS_REGION", "us-east-1")

# Session config
SESSION_TTL_HOURS = int(os.environ.get("SESSION_TTL_HOURS", "24"))

# Matching config
MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", "0.70"))
MAX_MATCHES_RETURNED = int(os.environ.get("MAX_MATCHES_RETURNED", "3"))

# Rate limiting
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20"))

# Supported languages: display name -> Amazon Transcribe language code
SUPPORTED_LANGUAGES = {
    "hindi": "hi-IN",
    "english": "en-IN",
    "tamil": "ta-IN",
    "telugu": "te-IN",
    "bengali": "bn-IN",
    "marathi": "mr-IN",
    "gujarati": "gu-IN",
    "kannada": "kn-IN",
    "malayalam": "ml-IN",
    "punjabi": "pa-IN",
}

# Reverse mapping: Transcribe code -> display name
LANGUAGE_CODE_TO_NAME = {v: k for k, v in SUPPORTED_LANGUAGES.items()}
