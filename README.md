# KaamConnect

Voice-first, multilingual job matching for India's blue-collar workers. Built for the **AI for Bharat Hackathon 2025** using 12+ AWS services.

**Live Demo:** [kaamconnect.rahulsingh.xyz](https://kaamconnect.rahulsingh.xyz)

## How It Works

```
Voice/Text → API Gateway → Lambda → Amazon Transcribe → Amazon Bedrock → DynamoDB → Response
```

1. User sends a voice note or text in any of 10 Indian languages
2. **Voice Processor** uploads audio to S3, runs Amazon Transcribe, returns text
3. **Entity Extractor** sends text to Amazon Bedrock (Nova Micro) — extracts job_type, location, salary, skills
4. If info incomplete, asks follow-up questions. If complete:
   - **Worker**: Matcher scores all jobs (weighted: job_type 30%, location 25%, salary 20%, availability 15%, skills 10%) → returns top 3
   - **Employer**: Creates a job posting in DynamoDB
5. Worker selects a match → gets employer contact details

## Architecture

| Component | Service | Region |
|-----------|---------|--------|
| Frontend | S3 + CloudFront + ACM (HTTPS) | ap-south-1 |
| Web Chat API | API Gateway (REST) → Lambda | ap-south-1 |
| WhatsApp API | AWS EUMS → SNS → Lambda | us-east-1 → ap-south-1 |
| Compute | 6 Lambda functions (Python 3.12, ARM64) | ap-south-1 |
| Database | DynamoDB (3 tables, PAY_PER_REQUEST) | ap-south-1 |
| Voice → Text | Amazon Transcribe (10 languages) | ap-south-1 |
| AI/NLP | Amazon Bedrock (Nova Micro) | ap-south-1 |
| Voice storage | S3 (auto-delete after 1 day) | ap-south-1 |
| Messaging | SNS + SQS (cross-region, DLQ) | both |
| Monitoring | CloudWatch dashboards | ap-south-1 |
| IaC | AWS CDK (Python, 4 stacks) | — |

## Supported Languages

Hindi, English, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam, Punjabi

## Code Structure

```
src/
├── handlers/          # Lambda entry points (6 functions)
├── services/          # Business logic
│   ├── routing_service.py        # Conversation state machine
│   ├── voice_service.py          # Transcription pipeline
│   ├── extraction_service.py     # Bedrock entity extraction
│   ├── matching_service.py       # Multi-dimensional scoring
│   ├── response_service.py       # Multilingual response templates
│   ├── session_service.py        # Session lifecycle
│   ├── web_chat_service.py       # Web chat adapter
│   └── contact_exchange_service.py
└── common/            # Shared Lambda layer
    ├── models/        # Dataclasses (Session, JobPosting, UserProfile)
    ├── repositories/  # DynamoDB access layer
    └── clients/       # AWS SDK wrappers (S3, Transcribe, Bedrock, EUMS)

infra/                 # AWS CDK stacks
web/                   # Frontend (landing page + chat UI)
prompts/               # Bedrock prompt templates
scripts/               # Seed data
```

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) or pip
- AWS CLI configured
- AWS CDK CLI (`npm install -g aws-cdk`)

### 1. Configure environment

```bash
cp .env.example .env
# Fill in your AWS account ID, EUMS ARN, and other values
```

### 2. Install dependencies

```bash
cd infra
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 3. Deploy

```bash
cd infra
cdk bootstrap   # First time only
cdk deploy --all
```

### 4. Seed test data

```bash
python scripts/seed_jobs.py
```

Creates 20 sample job postings across Bangalore, Mumbai, Delhi, Chennai, Hyderabad, Kolkata.

## Cost Estimate

~$16.40 per 1,000 interactions. Main costs: Transcribe ($6) + Bedrock ($2) + EUMS messaging ($8.40).

## Team

- Rajarshi Roy
- Rahul Kumar Singh
