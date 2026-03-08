import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    Stack,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_sns_subscriptions as sns_subs,
)
from constructs import Construct

from stacks.api_stack import ApiStack
from stacks.foundation_stack import FoundationStack


class ProcessingStack(Stack):
    """Lambda functions for message processing pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        foundation: FoundationStack,
        api: ApiStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Paths
        project_root = Path(__file__).parent.parent.parent
        src_path = project_root / "src"

        # === Shared Lambda Layer from src/common ===
        # Lambda layers require Python packages under python/ subdirectory
        # CDK bundling copies src/common into python/common at synth time
        self.common_layer = lambda_.LayerVersion(
            self,
            "CommonLayer",
            code=lambda_.Code.from_asset(
                str(src_path / "common"),
                bundling=BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "mkdir -p /asset-output/python/common && cp -r . /asset-output/python/common/",
                    ],
                ),
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            compatible_architectures=[lambda_.Architecture.ARM_64],
            description="KaamConnect shared common library",
        )

        # Common environment variables for all Lambdas
        common_env = {
            "BEDROCK_REGION": "ap-south-1",
            "BEDROCK_MODEL_ID": "apac.amazon.nova-micro-v1:0",
            "SESSIONS_TABLE": foundation.sessions_table.table_name,
            "JOB_POSTINGS_TABLE": foundation.job_postings_table.table_name,
            "USER_PROFILES_TABLE": foundation.user_profiles_table.table_name,
            "S3_VOICE_BUCKET": foundation.voice_bucket.bucket_name,
            "SNS_TOPIC_ARN": foundation.incoming_messages_topic.topic_arn,
            "EUMS_PHONE_NUMBER_ARN": os.environ.get("EUMS_PHONE_NUMBER_ARN", ""),
            "EUMS_REGION": os.environ.get("EUMS_REGION", "us-east-1"),
        }

        # === Message Router Lambda ===
        self.message_router = self._create_lambda(
            "MessageRouter",
            handler="handlers.message_router.handler",
            code_path=str(src_path),
            env={**common_env},
            timeout=120,  # Must exceed voice_processor timeout (90s) for synchronous chain
            memory=256,
        )
        # Triggered by SNS, with DLQ for failed messages
        foundation.incoming_messages_topic.add_subscription(
            sns_subs.LambdaSubscription(
                self.message_router,
                dead_letter_queue=foundation.dlq,
            )
        )
        # Permissions: read/write sessions, invoke other lambdas
        foundation.sessions_table.grant_read_write_data(self.message_router)
        foundation.user_profiles_table.grant_read_write_data(self.message_router)

        # === Voice Processor Lambda ===
        self.voice_processor = self._create_lambda(
            "VoiceProcessor",
            handler="handlers.voice_processor.handler",
            code_path=str(src_path),
            env={**common_env},
            timeout=90,  # Voice processing: download + S3 upload + Transcribe polling
            memory=512,
        )
        # Permissions: S3 read/write/delete, Transcribe
        foundation.voice_bucket.grant_read_write(self.voice_processor)
        foundation.voice_bucket.grant_delete(self.voice_processor)
        self.voice_processor.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "transcribe:StartTranscriptionJob",
                    "transcribe:GetTranscriptionJob",
                    "transcribe:DeleteTranscriptionJob",
                ],
                resources=["*"],
            )
        )
        # EUMS media download
        self.voice_processor.add_to_role_policy(
            iam.PolicyStatement(
                actions=["social-messaging:GetWhatsAppMessageMedia"],
                resources=["*"],
            )
        )

        # === Entity Extractor Lambda ===
        self.entity_extractor = self._create_lambda(
            "EntityExtractor",
            handler="handlers.entity_extractor.handler",
            code_path=str(src_path),
            env={**common_env},
            timeout=30,
            memory=256,
        )
        # Permissions: Bedrock InvokeModel (us-east-1)
        self.entity_extractor.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:ap-south-1:*:inference-profile/{common_env['BEDROCK_MODEL_ID']}",
                    "arn:aws:bedrock:*::foundation-model/amazon.nova-micro-v1:0",
                ],
            )
        )
        foundation.sessions_table.grant_read_write_data(self.entity_extractor)

        # === Matcher Lambda ===
        self.matcher = self._create_lambda(
            "Matcher",
            handler="handlers.matcher.handler",
            code_path=str(src_path),
            env={**common_env},
            timeout=30,
            memory=256,
        )
        # Permissions: read job postings (including GSIs), read user profiles
        foundation.job_postings_table.grant_read_data(self.matcher)
        foundation.user_profiles_table.grant_read_data(self.matcher)

        # === Response Generator Lambda ===
        self.response_generator = self._create_lambda(
            "ResponseGenerator",
            handler="handlers.response_generator.handler",
            code_path=str(src_path),
            env={**common_env},
            timeout=30,
            memory=256,
        )
        # Permissions: EUMS send, Bedrock for multilingual response generation
        self.response_generator.add_to_role_policy(
            iam.PolicyStatement(
                actions=["social-messaging:SendWhatsAppMessage"],
                resources=["*"],
            )
        )
        self.response_generator.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:ap-south-1:*:inference-profile/{common_env['BEDROCK_MODEL_ID']}",
                    "arn:aws:bedrock:*::foundation-model/amazon.nova-micro-v1:0",
                ],
            )
        )
        foundation.sessions_table.grant_read_data(self.response_generator)

        # === Cross-Lambda invocation permissions ===
        # Message Router can invoke all other lambdas
        self.voice_processor.grant_invoke(self.message_router)
        self.entity_extractor.grant_invoke(self.message_router)
        self.matcher.grant_invoke(self.message_router)
        self.response_generator.grant_invoke(self.message_router)

        # Update env vars with function names for cross-invocation
        self.message_router.add_environment(
            "VOICE_PROCESSOR_FUNCTION", self.voice_processor.function_name
        )
        self.message_router.add_environment(
            "ENTITY_EXTRACTOR_FUNCTION", self.entity_extractor.function_name
        )
        self.message_router.add_environment(
            "MATCHER_FUNCTION", self.matcher.function_name
        )
        self.message_router.add_environment(
            "RESPONSE_GENERATOR_FUNCTION", self.response_generator.function_name
        )

        # === Web Chat Lambda ===
        self.web_chat = self._create_lambda(
            "WebChat",
            handler="handlers.web_chat.handler",
            code_path=str(src_path),
            env={**common_env},
            timeout=120,
            memory=512,
        )
        foundation.sessions_table.grant_read_write_data(self.web_chat)
        foundation.job_postings_table.grant_read_write_data(self.web_chat)
        foundation.user_profiles_table.grant_read_write_data(self.web_chat)
        foundation.voice_bucket.grant_read_write(self.web_chat)
        foundation.voice_bucket.grant_delete(self.web_chat)
        self.web_chat.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "transcribe:StartTranscriptionJob",
                    "transcribe:GetTranscriptionJob",
                    "transcribe:DeleteTranscriptionJob",
                ],
                resources=["*"],
            )
        )
        self.web_chat.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:ap-south-1:*:inference-profile/{common_env['BEDROCK_MODEL_ID']}",
                    "arn:aws:bedrock:*::foundation-model/amazon.nova-micro-v1:0",
                ],
            )
        )

        # === Web Chat API Gateway ===
        self.chat_api = apigw.LambdaRestApi(
            self,
            "ChatApi",
            rest_api_name="kaamconnect-chat",
            handler=self.web_chat,
            proxy=False,
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=50,
                throttling_burst_limit=100,
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type"],
            ),
        )

        chat_resource = self.chat_api.root.add_resource("chat")
        chat_resource.add_method("POST", apigw.LambdaIntegration(self.web_chat))
        chat_resource.add_method("GET", apigw.LambdaIntegration(self.web_chat))

        CfnOutput(self, "ChatApiUrl", value=self.chat_api.url, description="Web Chat API URL")

    def _create_lambda(
        self,
        id: str,
        handler: str,
        code_path: str,
        env: dict,
        timeout: int = 30,
        memory: int = 256,
    ) -> lambda_.Function:
        """Create a Lambda function with common configuration."""
        fn = lambda_.Function(
            self,
            id,
            function_name=f"kaamconnect-{id.lower().replace('_', '-')}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler=handler,
            code=lambda_.Code.from_asset(code_path),
            layers=[self.common_layer],
            environment=env,
            timeout=Duration.seconds(timeout),
            memory_size=memory,
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        return fn
