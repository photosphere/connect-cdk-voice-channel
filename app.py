#!/usr/bin/env python3
import os

import aws_cdk as cdk

from connect_cdk_voice_channel.connect_cdk_voice_channel_stack import ConnectCdkVoiceChannelStack


app = cdk.App()
# CloudFormation Stack 名称：优先使用经过合法化处理的 stack_name，
# 若不存在则回退到 tenant_name（保持向后兼容）。
stack_id = os.environ.get("stack_name") or os.environ["tenant_name"]
ConnectCdkVoiceChannelStack(app, stack_id, description=os.environ.get("tenant_description", "")
                            # If you don't specify 'env', this stack will be environment-agnostic.
                            # Account/Region-dependent features and context lookups will not work,
                            # but a single synthesized template can be deployed anywhere.

                            # Uncomment the next line to specialize this stack for the AWS Account
                            # and Region that are implied by the current CLI configuration.

                            # env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),

                            # Uncomment the next line if you know exactly what Account and Region you
                            # want to deploy the stack to. */

                            # env=cdk.Environment(account='123456789012', region='us-east-1'),

                            # For more information, see https://docs.aws.amazon.com/cdk/latest/guide/environments.html
                            )

app.synth()
