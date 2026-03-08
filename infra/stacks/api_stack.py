import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

from aws_cdk import (
    Stack,
    aws_apigateway as apigw,
    aws_iam as iam,
)
from constructs import Construct

from stacks.foundation_stack import FoundationStack


class ApiStack(Stack):
    """API Gateway for WhatsApp webhook. No WAF — uses API GW throttling (free)."""

    def __init__(self, scope: Construct, construct_id: str, foundation: FoundationStack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # === API Gateway REST API ===
        self.api = apigw.RestApi(
            self,
            "WebhookApi",
            rest_api_name="kaamconnect-webhook",
            description="KaamConnect WhatsApp webhook endpoint",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=50,   # 50 req/sec (free, replaces WAF)
                throttling_burst_limit=100,
            ),
        )

        # IAM role for API Gateway to publish to SNS
        api_sns_role = iam.Role(
            self,
            "ApiGatewaySnSRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
        )
        foundation.incoming_messages_topic.grant_publish(api_sns_role)

        # POST /webhook -> SNS direct integration
        # Returns 200 immediately, processing happens async via SNS -> Lambda
        webhook_resource = self.api.root.add_resource("webhook")

        sns_integration = apigw.AwsIntegration(
            service="sns",
            integration_http_method="POST",
            path=f"{self.account}/{foundation.incoming_messages_topic.topic_name}",
            options=apigw.IntegrationOptions(
                credentials_role=api_sns_role,
                request_parameters={
                    "integration.request.header.Content-Type": "'application/x-www-form-urlencoded'",
                },
                request_templates={
                    "application/json": (
                        "Action=Publish"
                        f"&TopicArn=$util.urlEncode('{foundation.incoming_messages_topic.topic_arn}')"
                        "&Message=$util.urlEncode($input.body)"
                    ),
                },
                integration_responses=[
                    apigw.IntegrationResponse(
                        status_code="200",
                        response_templates={"application/json": '{"status": "ok"}'},
                    )
                ],
            ),
        )

        webhook_resource.add_method(
            "POST",
            sns_integration,
            method_responses=[
                apigw.MethodResponse(
                    status_code="200",
                    response_models={"application/json": apigw.Model.EMPTY_MODEL},
                )
            ],
        )

        # GET /webhook for WhatsApp webhook verification
        # Validates hub.verify_token before echoing hub.challenge
        webhook_resource.add_method(
            "GET",
            apigw.MockIntegration(
                integration_responses=[
                    apigw.IntegrationResponse(
                        status_code="200",
                        response_templates={
                            "application/json": "$input.params('hub.challenge')",
                        },
                    ),
                    apigw.IntegrationResponse(
                        status_code="403",
                        selection_pattern="403",
                        response_templates={
                            "application/json": '{"error": "Forbidden"}',
                        },
                    ),
                ],
                request_templates={
                    "application/json": (
                        "#set($token = $input.params('hub.verify_token'))\n"
                        f"#if($token == '{os.environ.get('WEBHOOK_VERIFY_TOKEN', 'KAAMCONNECT_VERIFY_TOKEN')}')\n"
                        '{"statusCode": 200}\n'
                        "#else\n"
                        '{"statusCode": 403}\n'
                        "#end"
                    ),
                },
            ),
            method_responses=[
                apigw.MethodResponse(status_code="200"),
                apigw.MethodResponse(status_code="403"),
            ],
        )
