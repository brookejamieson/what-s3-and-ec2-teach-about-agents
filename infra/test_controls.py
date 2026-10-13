"""Deterministic test of every control, with no model in the loop.

Each step calls a gateway tool directly and prints ALLOW/DENY. This proves the
infrastructure before any agent prompt is tested.
"""
import json
import sys
import time
import uuid

from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient

sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import ADMIN_PROFILE, REGION, load_state  # noqa: E402

st = load_state()
DEV = st["instances"]["dev-api-scratch"]
PROD = st["instances"]["prod-web-1"]


def gateway(session_id):
    return MCPClient(lambda: aws_iam_streamablehttp_client(
        endpoint=st["gateway_url"], aws_region=REGION, aws_service="bedrock-agentcore",
        aws_profile=ADMIN_PROFILE, headers={"x-amzn-bedrock-agentcore-policy-session-id": session_id}))


def call(c, name, args):
    r = c.call_tool_sync(tool_use_id=str(uuid.uuid4()), name=name, arguments=args)
    text = " ".join(x.get("text", "") for x in r["content"])[:300].replace("\n", " ")
    return r["status"], text


READ = ("AwsMcp___aws___run_script",
        {"code": f"r = await call_boto3(service_name='ec2', operation_name='DescribeInstances', "
                 f"params={{'InstanceIds': ['{DEV}', '{PROD}']}})\n"
                 f"result = [(i['InstanceId'], i['State']['Name']) for x in r['Reservations'] for i in x['Instances']]\nresult"})

results = []
with gateway(f"test-a-{uuid.uuid4()}") as c:
    print("tools listed:", sorted(t.tool_name for t in c.list_tools_sync()))
    OTHER = st["instances"]["dev-load-test"]
    results.append(("1 stop dev with no look (Dogwood should deny)",
                    *call(c, "InstanceTools___stop_instance", {"instanceId": DEV})))
    results.append(("2 read the account with run_script", *call(c, *READ)))
    results.append(("3 terminate dev (Cedar forbid should deny)",
                    *call(c, "InstanceTools___terminate_instance", {"instanceId": DEV})))
    results.append(("4 describe dev-api-scratch", *call(c, "InstanceTools___describe_instance", {"instanceId": DEV})))
    results.append(("5 describe prod", *call(c, "InstanceTools___describe_instance", {"instanceId": PROD})))
    time.sleep(3)  # the response event is recorded shortly after the call
    results.append(("6 stop a DIFFERENT dev box it never looked at (Dogwood should deny)",
                    *call(c, "InstanceTools___stop_instance", {"instanceId": OTHER})))
    results.append(("7 stop PROD after looking at it (policy allows, IAM should refuse)",
                    *call(c, "InstanceTools___stop_instance", {"instanceId": PROD})))
    if "--stop-dev" in sys.argv:
        results.append(("8 stop dev-api-scratch after looking at it (should succeed)",
                        *call(c, "InstanceTools___stop_instance", {"instanceId": DEV})))

for label, status, text in results:
    print(f"\n{label}\n  -> {status}: {text}")
