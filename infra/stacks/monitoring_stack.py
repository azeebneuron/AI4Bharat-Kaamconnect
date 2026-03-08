from aws_cdk import (
    Stack,
    aws_budgets as budgets,
)
from constructs import Construct

from stacks.foundation_stack import FoundationStack
from stacks.processing_stack import ProcessingStack


class MonitoringStack(Stack):
    """Budget alert only. No dashboard or alarms (saves ~$9.50/month).

    Use CloudWatch Logs console directly — it's free.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        foundation: FoundationStack,
        processing: ProcessingStack,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Budget alert at $150 of $200 hackathon credits — free to create
        budgets.CfnBudget(
            self,
            "BudgetAlert",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=150,
                    unit="USD",
                ),
                budget_name="kaamconnect-monthly-budget",
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=80,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            subscription_type="EMAIL",
                            address="kaamconnect-alerts@example.com",  # TODO: Set real email
                        ),
                    ],
                ),
            ],
        )
