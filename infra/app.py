#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.foundation_stack import FoundationStack
from stacks.api_stack import ApiStack
from stacks.processing_stack import ProcessingStack
from stacks.monitoring_stack import MonitoringStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region="ap-south-1",
)

foundation = FoundationStack(app, "KaamConnect-Foundation", env=env)
api = ApiStack(app, "KaamConnect-Api", foundation=foundation, env=env)
processing = ProcessingStack(app, "KaamConnect-Processing", foundation=foundation, api=api, env=env)
monitoring = MonitoringStack(app, "KaamConnect-Monitoring", foundation=foundation, processing=processing, env=env)

app.synth()
