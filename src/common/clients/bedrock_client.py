import json

import boto3

from common import config
from common.logger import get_logger

logger = get_logger(__name__)


class BedrockClient:
    """Wrapper for Amazon Bedrock InvokeModel API.

    Supports both Claude (Anthropic) and Amazon Nova model families.
    Detects the model family from the model ID and formats requests accordingly.
    """

    def __init__(self):
        self._bedrock = boto3.client("bedrock-runtime", region_name=config.BEDROCK_REGION)
        self._model_id = config.BEDROCK_MODEL_ID
        self._is_nova = "nova" in self._model_id.lower()

    def invoke_claude(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        """Invoke a model and return the text response.

        Works with both Claude and Nova models transparently.
        """
        if self._is_nova:
            return self._invoke_nova(system_prompt, user_message, max_tokens, temperature)
        return self._invoke_claude(system_prompt, user_message, max_tokens, temperature)

    def invoke_claude_with_history(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        """Invoke a model with multi-turn conversation history."""
        if self._is_nova:
            return self._invoke_nova_with_history(system_prompt, messages, max_tokens, temperature)
        return self._invoke_claude_with_history(system_prompt, messages, max_tokens, temperature)

    # ---- Claude (Anthropic) format ----

    def _invoke_claude(self, system_prompt, user_message, max_tokens, temperature):
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        })
        response = self._bedrock.invoke_model(
            modelId=self._model_id, body=body,
            contentType="application/json", accept="application/json",
        )
        response_body = json.loads(response["body"].read())
        content = response_body.get("content", [])
        text_parts = [block["text"] for block in content if block.get("type") == "text"]
        self._log_usage(response_body.get("usage", {}))
        return "\n".join(text_parts)

    def _invoke_claude_with_history(self, system_prompt, messages, max_tokens, temperature):
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": messages,
        })
        response = self._bedrock.invoke_model(
            modelId=self._model_id, body=body,
            contentType="application/json", accept="application/json",
        )
        response_body = json.loads(response["body"].read())
        content = response_body.get("content", [])
        text_parts = [block["text"] for block in content if block.get("type") == "text"]
        self._log_usage(response_body.get("usage", {}))
        return "\n".join(text_parts)

    # ---- Amazon Nova format ----

    def _invoke_nova(self, system_prompt, user_message, max_tokens, temperature):
        body = json.dumps({
            "system": [{"text": system_prompt}],
            "messages": [{"role": "user", "content": [{"text": user_message}]}],
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        })
        response = self._bedrock.invoke_model(
            modelId=self._model_id, body=body,
            contentType="application/json", accept="application/json",
        )
        response_body = json.loads(response["body"].read())
        output = response_body.get("output", {}).get("message", {})
        content = output.get("content", [])
        text_parts = [block["text"] for block in content if "text" in block]
        self._log_usage(response_body.get("usage", {}))
        return "\n".join(text_parts)

    def _invoke_nova_with_history(self, system_prompt, messages, max_tokens, temperature):
        # Convert Claude-format messages to Nova format
        nova_messages = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                nova_messages.append({"role": msg["role"], "content": [{"text": content}]})
            elif isinstance(content, list):
                nova_content = [{"text": block.get("text", "")} for block in content if isinstance(block, dict)]
                nova_messages.append({"role": msg["role"], "content": nova_content})
            else:
                nova_messages.append({"role": msg["role"], "content": [{"text": str(content)}]})

        body = json.dumps({
            "system": [{"text": system_prompt}],
            "messages": nova_messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        })
        response = self._bedrock.invoke_model(
            modelId=self._model_id, body=body,
            contentType="application/json", accept="application/json",
        )
        response_body = json.loads(response["body"].read())
        output = response_body.get("output", {}).get("message", {})
        content = output.get("content", [])
        text_parts = [block["text"] for block in content if "text" in block]
        self._log_usage(response_body.get("usage", {}))
        return "\n".join(text_parts)

    def _log_usage(self, usage: dict):
        logger.info(
            "Bedrock invocation complete",
            extra={
                "input_tokens": usage.get("input_tokens") or usage.get("inputTokens"),
                "output_tokens": usage.get("output_tokens") or usage.get("outputTokens"),
            },
        )
