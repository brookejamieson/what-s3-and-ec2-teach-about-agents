"""Step 2: AgentCore Gateway with the AWS MCP Server as a target.

This is the build's biggest unknown: the gateway signs requests to an MCP
server target with its own role (SigV4). The AWS MCP Server isn't in the
documented list of SigV4 targets, so this script tries it and reports.

Inbound auth is AWS_IAM, so the agent connects with
mcp_proxy_for_aws.client.aws_iam_streamablehttp_client.
"""
import sys

from botocore.exceptions import ClientError

from common import (AWS_MCP_ENDPOINT, GATEWAY_NAME, REGION, TAG, load_state,
                    save_state, session, wait_for)

ctl = session().client("bedrock-agentcore-control")
st = load_state()


def find_gateway():
    for g in ctl.list_gateways()["items"]:
        if g["name"] == GATEWAY_NAME:
            return ctl.get_gateway(gatewayIdentifier=g["gatewayId"])
    return None


gw = find_gateway()
if not gw:
    gw = ctl.create_gateway(
        name=GATEWAY_NAME,
        description="Talk demo gateway: AWS MCP Server reads + instance tools",
        roleArn=st["gateway_role_arn"],
        protocolType="MCP",
        authorizerType="AWS_IAM",
        exceptionLevel="DEBUG",
        tags=TAG,
    )
    print("created gateway", gw["gatewayId"])
gw_id = gw["gatewayId"]
gw = wait_for(lambda: ctl.get_gateway(gatewayIdentifier=gw_id),
              lambda r: r["status"] in ("READY", "FAILED"), "gateway READY")
print("gateway", gw["status"], gw["gatewayUrl"])
save_state(gateway_id=gw_id, gateway_url=gw["gatewayUrl"], gateway_arn=gw["gatewayArn"])


def find_target(name):
    for t in ctl.list_gateway_targets(gatewayIdentifier=gw_id)["items"]:
        if t["name"] == name:
            return ctl.get_gateway_target(gatewayIdentifier=gw_id, targetId=t["targetId"])
    return None


tgt = find_target("AwsMcp")
if not tgt:
    try:
        tgt = ctl.create_gateway_target(
            gatewayIdentifier=gw_id,
            name="AwsMcp",
            description="The AWS MCP Server from the Agent Toolkit for AWS",
            targetConfiguration={"mcp": {"mcpServer": {"endpoint": AWS_MCP_ENDPOINT}}},
            credentialProviderConfigurations=[{
                "credentialProviderType": "GATEWAY_IAM_ROLE",
                "credentialProvider": {"iamCredentialProvider": {"service": "aws-mcp", "region": REGION}},
            }],
        )
    except ClientError as e:
        print("CREATE TARGET FAILED:", e)
        sys.exit(1)
tid = tgt["targetId"]
tgt = wait_for(lambda: ctl.get_gateway_target(gatewayIdentifier=gw_id, targetId=tid),
               lambda r: r["status"] not in ("CREATING", "UPDATING", "SYNCHRONIZING"),
               "target ready", timeout=300)
print("target AwsMcp", tgt["status"], tgt.get("statusReasons"))
save_state(aws_mcp_target_id=tid)
