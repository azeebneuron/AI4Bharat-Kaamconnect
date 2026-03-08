from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_sns as sns,
)
from constructs import Construct


class FoundationStack(Stack):
    """Foundation infrastructure: DynamoDB tables, S3 bucket, SNS topic."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # === DynamoDB Tables ===

        # Sessions table: PK=phone_number, SK=session_id, TTL=expires_at
        self.sessions_table = dynamodb.Table(
            self,
            "SessionsTable",
            table_name="kaamconnect-sessions",
            partition_key=dynamodb.Attribute(name="phone_number", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Job Postings table: PK=job_id, TTL=expires_at
        self.job_postings_table = dynamodb.Table(
            self,
            "JobPostingsTable",
            table_name="kaamconnect-job-postings",
            partition_key=dynamodb.Attribute(name="job_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # GSI1: Location + JobType index for matching queries
        self.job_postings_table.add_global_secondary_index(
            index_name="gsi1-location-jobtype",
            partition_key=dynamodb.Attribute(name="gsi1pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="gsi1sk", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # GSI2: Status + CreatedAt index for cleanup and listing
        self.job_postings_table.add_global_secondary_index(
            index_name="gsi2-status-created",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # User Profiles table: PK=phone_number
        self.user_profiles_table = dynamodb.Table(
            self,
            "UserProfilesTable",
            table_name="kaamconnect-user-profiles",
            partition_key=dynamodb.Attribute(name="phone_number", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # === S3 Bucket for voice files ===
        self.voice_bucket = s3.Bucket(
            self,
            "VoiceBucket",
            bucket_name=None,  # Auto-generate unique name
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteVoiceFilesAfter1Day",
                    expiration=Duration.days(1),
                    prefix="voice/",
                )
            ],
        )

        # === SNS Topic for incoming messages ===
        self.incoming_messages_topic = sns.Topic(
            self,
            "IncomingMessagesTopic",
            topic_name="kaamconnect-incoming-messages",
            master_key=None,  # Use AWS managed encryption via policy below
        )

        # === Dead Letter Queue for failed message processing ===
        from aws_cdk import aws_sqs as sqs
        self.dlq = sqs.Queue(
            self,
            "MessageProcessingDLQ",
            queue_name="kaamconnect-message-dlq",
            retention_period=Duration.days(14),
        )
