"""Shared settings for the talk's sandbox setup scripts.

Every resource these scripts create is tagged project=aws-ai-agents-talk, so
teardown.py can find it again.
"""
import json
import os
import time

import boto3

REGION = "us-east-1"
# The profile that builds the sandbox. It needs permission to create IAM roles, EC2,
# S3, Lambda and AgentCore resources. Set TALK_ADMIN_PROFILE to use another profile.
ADMIN_PROFILE = os.environ.get("TALK_ADMIN_PROFILE", "default")
TAG = {"project": "aws-ai-agents-talk"}
TAG_LIST = [{"Key": k, "Value": v} for k, v in TAG.items()]

# Names
READONLY_ROLE = "talk-readonly"            # what the agent's AWS MCP Server reads run as
STOP_TOOL_ROLE = "talk-instance-tools"     # Lambda execution role: can only stop env=dev
GATEWAY_ROLE = "talk-gateway"              # gateway service role
GATEWAY_NAME = "talk-gateway"
POLICY_ENGINE_NAME = "talk_policy_engine"
INSTANCE_TOOLS_FN = "talk-instance-tools"
AWS_MCP_ENDPOINT = "https://aws-mcp.us-east-1.api.aws/mcp"

STATE_FILE = __import__("pathlib").Path(__file__).with_name("state.json")


def session():
    return boto3.Session(profile_name=ADMIN_PROFILE, region_name=REGION)


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(**kv):
    s = load_state()
    s.update(kv)
    STATE_FILE.write_text(json.dumps(s, indent=2))
    return s


def account_id() -> str:
    return session().client("sts").get_caller_identity()["Account"]


def wait_for(fn, ok, what, timeout=300, every=5):
    """Poll fn() until ok(result) is true."""
    start = time.time()
    while True:
        r = fn()
        if ok(r):
            return r
        if time.time() - start > timeout:
            raise TimeoutError(f"timed out waiting for {what}: {r}")
        time.sleep(every)
