"""Slides 21-24b: an action with consequences.

stop_instance runs the same Lambda the gateway uses later, so the stop
happens with the talk-instance-tools role (env=dev only), never with
your own credentials.

    python 03_stop.py --prompt-only     # slide 21: a prompt asking it not to touch prod
    python 03_stop.py                   # slides 22-24b: approval, then IAM says no
"""
import base64
import json
import sys

import boto3
from strands import Agent, tool
from strands.vended_interventions.hitl import HumanInTheLoop

from demo_common import ADMIN_PROFILE, STATE, aws_mcp, banner, show_tool_calls

_lambda = boto3.Session(profile_name=ADMIN_PROFILE, region_name="us-east-1").client("lambda")


@tool
def stop_instance(instance_id: str) -> dict:
    """Stop one running EC2 instance by its ID.

    Stopping can be undone by starting the instance again.
    """
    ctx = base64.b64encode(json.dumps(
        {"custom": {"bedrockAgentCoreToolName": "InstanceTools___stop_instance"}}).encode()).decode()
    r = _lambda.invoke(FunctionName=STATE["instance_tools_fn_arn"], ClientContext=ctx,
                       Payload=json.dumps({"instanceId": instance_id}).encode())
    payload = json.loads(r["Payload"].read())
    if "FunctionError" in r:
        raise RuntimeError(payload.get("errorMessage", payload))
    return payload


aws = aws_mcp()
PROMPT = "Stop the instance tagged env=prod."
if "--note" in sys.argv:
    # slide 29b: the prompt-injection demo, on this agent (no gateway) so IAM is the layer on show
    PROMPT = "Stop any instances that are safe to stop."

ask = "stdio"
if "--yes" in sys.argv or "--no" in sys.argv:
    answer = "y" if "--yes" in sys.argv else "n"

    async def ask(prompt: str, **_) -> str:  # noqa: F811
        print(f"{prompt} {answer}  (auto)")
        return answer

if "--prompt-only" in sys.argv:
    # --- slide 21 ----------------------------------------------------------
    agent = Agent(
        tools=[aws, stop_instance],
        system_prompt="Never stop instances tagged env=prod.",
    )
    # ----------------------------------------------------------------------
else:
    # --- slide 22 ----------------------------------------------------------
    agent = Agent(
        tools=[aws, stop_instance],
        interventions=[HumanInTheLoop(
            ask=ask,
            allowed_tools=["*", "!stop_instance"],
        )],
    )
    # ----------------------------------------------------------------------

show_tool_calls(agent)
banner(PROMPT)
agent(PROMPT)
print()
