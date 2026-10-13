"""Step 1: IAM roles for the demo.

talk-readonly        ReadOnlyAccess. The agent's account reads run as this role
                     (local profile `talk-readonly` assumes it).
talk-instance-tools  Lambda execution role for stop_instance / terminate_instance.
                     It can stop instances tagged env=dev and nothing else.
                     It has no terminate permission at all (slide 25's ban is
                     belt and braces).
talk-gateway         AgentCore Gateway service role: invokes the instance-tools
                     Lambda and signs calls to the AWS MCP Server (read-only).
"""
import json

from botocore.exceptions import ClientError

from common import (GATEWAY_ROLE, INSTANCE_TOOLS_FN, READONLY_ROLE, REGION,
                    STOP_TOOL_ROLE, TAG_LIST, account_id, save_state, session)

iam = session().client("iam")
ACCOUNT = account_id()
# Any IAM principal in this account that is allowed sts:AssumeRole on talk-readonly
# can use it. That is how the local `talk-readonly` profile reaches it.
ACCOUNT_PRINCIPAL = f"arn:aws:iam::{ACCOUNT}:root"


def ensure_role(name, trust, managed=(), inline=None, description=""):
    try:
        role = iam.create_role(
            RoleName=name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description=description,
            Tags=TAG_LIST,
            MaxSessionDuration=3600 * 4,
        )["Role"]
        print(f"created role {name}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
        iam.update_assume_role_policy(RoleName=name, PolicyDocument=json.dumps(trust))
        role = iam.get_role(RoleName=name)["Role"]
        print(f"role {name} exists, trust policy refreshed")
    for arn in managed:
        iam.attach_role_policy(RoleName=name, PolicyArn=arn)
    if inline:
        iam.put_role_policy(RoleName=name, PolicyName=f"{name}-inline",
                            PolicyDocument=json.dumps(inline))
    return role["Arn"]


readonly_arn = ensure_role(
    READONLY_ROLE,
    trust={
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Principal": {"AWS": ACCOUNT_PRINCIPAL}, "Action": "sts:AssumeRole"},
            {"Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
             "Action": "sts:AssumeRole",
             "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}}},
        ],
    },
    managed=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
    description="Read-only role the demo agent uses to look at the account",
)

stop_arn = ensure_role(
    STOP_TOOL_ROLE,
    trust={
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                       "Action": "sts:AssumeRole"}],
    },
    managed=["arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"],
    inline={
        "Version": "2012-10-17",
        "Statement": [
            {   # This is the statement on slide 23.
                "Sid": "StopOnlyDevInstances",
                "Effect": "Allow",
                "Action": "ec2:StopInstances",
                "Resource": "arn:aws:ec2:*:*:instance/*",
                "Condition": {"StringEquals": {"aws:ResourceTag/env": "dev"}},
            },
            {"Sid": "LookUpInstances", "Effect": "Allow",
             "Action": "ec2:DescribeInstances", "Resource": "*"},
        ],
    },
    description="Instance tools Lambda: may stop env=dev instances only",
)

gateway_arn = ensure_role(
    GATEWAY_ROLE,
    trust={
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                       "Action": "sts:AssumeRole",
                       "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}}}],
    },
    managed=["arn:aws:iam::aws:policy/ReadOnlyAccess"],
    inline={
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "InvokeInstanceTools", "Effect": "Allow",
            "Action": "lambda:InvokeFunction",
            "Resource": f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{INSTANCE_TOOLS_FN}",
        }],
    },
    description="AgentCore Gateway role for the talk demo",
)

save_state(account=ACCOUNT, readonly_role_arn=readonly_arn,
           stop_role_arn=stop_arn, gateway_role_arn=gateway_arn)
print(json.dumps({"readonly": readonly_arn, "instance_tools": stop_arn, "gateway": gateway_arn}, indent=2))
