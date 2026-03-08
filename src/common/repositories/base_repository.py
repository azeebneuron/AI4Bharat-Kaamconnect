from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

from common import config
from common.logger import get_logger

logger = get_logger(__name__)


class BaseRepository:
    """Base DynamoDB repository with common CRUD operations."""

    def __init__(self, table_name: str, region: Optional[str] = None):
        self._table_name = table_name
        self._dynamodb = boto3.resource("dynamodb", region_name=region or config.REGION)
        self._table = self._dynamodb.Table(table_name)

    def get_item(self, key: dict) -> Optional[dict]:
        response = self._table.get_item(Key=key)
        return response.get("Item")

    def put_item(self, item: dict) -> None:
        self._table.put_item(Item=item)

    def update_item(self, key: dict, updates: dict) -> dict:
        """Update specific attributes and return the updated item."""
        update_parts = []
        expression_values = {}
        expression_names = {}

        for i, (attr, value) in enumerate(updates.items()):
            placeholder = f":val{i}"
            name_placeholder = f"#attr{i}"
            update_parts.append(f"{name_placeholder} = {placeholder}")
            expression_values[placeholder] = value
            expression_names[name_placeholder] = attr

        response = self._table.update_item(
            Key=key,
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames=expression_names,
            ReturnValues="ALL_NEW",
        )
        return response["Attributes"]

    def delete_item(self, key: dict) -> None:
        self._table.delete_item(Key=key)

    def query(
        self,
        key_condition: Any,
        index_name: Optional[str] = None,
        filter_expression: Any = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {"KeyConditionExpression": key_condition}
        if index_name:
            kwargs["IndexName"] = index_name
        if filter_expression:
            kwargs["FilterExpression"] = filter_expression
        # DynamoDB Limit is applied BEFORE FilterExpression, so when filtering
        # we must not pass Limit to DynamoDB — instead we paginate fully and
        # apply the limit in Python after filtering.
        if limit and not filter_expression:
            kwargs["Limit"] = limit

        items = []
        response = self._table.query(**kwargs)
        items.extend(response.get("Items", []))

        # Handle pagination (required when using FilterExpression without Limit)
        while "LastEvaluatedKey" in response:
            if limit and len(items) >= limit:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
            response = self._table.query(**kwargs)
            items.extend(response.get("Items", []))

        if limit:
            items = items[:limit]
        return items

    def query_with_key(
        self,
        partition_key_name: str,
        partition_key_value: str,
        sort_key_condition: Any = None,
        index_name: Optional[str] = None,
        filter_expression: Any = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Convenience method for common query patterns."""
        key_condition = Key(partition_key_name).eq(partition_key_value)
        if sort_key_condition:
            key_condition = key_condition & sort_key_condition
        return self.query(key_condition, index_name, filter_expression, limit)
