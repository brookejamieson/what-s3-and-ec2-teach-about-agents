"""Shared pieces for the demo stages.

Not shown on slides. The slide code is the `agent = Agent(...)` part of each
stage file; this module keeps the terminal output readable on screen.
"""
import json
import logging
import os
import sys
import uuid

# Keep library tracebacks out of the recording; tool errors are still printed by show_tool_calls.
for _name in ("strands", "mcp", "httpx", "mcp_proxy_for_aws"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)

from mcp import StdioServerParameters, stdio_client
from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent
from strands.tools.mcp import MCPClient

REGION = "us-east-1"
# Local AWS profiles. The read-only one is what the agent reads the account with.
ADMIN_PROFILE = os.environ.get("TALK_ADMIN_PROFILE", "default")
READONLY_PROFILE = os.environ.get("TALK_READONLY_PROFILE", "talk-readonly")
HERE = os.path.dirname(os.path.abspath(__file__))
# Written by the scripts in ../infra. 01_first_agent.py runs without it.
_STATE_FILE = os.path.join(HERE, "..", "infra", "state.json")
STATE = json.load(open(_STATE_FILE)) if os.path.exists(_STATE_FILE) else {}

# ANSI styling for the recording terminal
DIM, BOLD, CYAN, RED, GREEN, YELLOW, RESET = (
    "\033[2m", "\033[1m", "\033[36m", "\033[31m", "\033[32m", "\033[33m", "\033[0m")


def aws_mcp(only=("aws___run_script",)):
    """The AWS MCP Server, through the MCP Proxy for AWS, on the read-only profile (slide 11)."""
    return MCPClient(
        lambda: stdio_client(StdioServerParameters(
            command="uvx",
            args=["mcp-proxy-for-aws@1.6.3", "https://aws-mcp.us-east-1.api.aws/mcp",
                  "--profile", READONLY_PROFILE, "--metadata", f"AWS_REGION={REGION}"],
        )),
        tool_filters={"allowed": list(only)} if only else None,
    )


def gateway_mcp(session_id=None):
    """All tools through AgentCore Gateway, with a Dogwood policy session (slides 25 to 29b)."""
    from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
    sid = session_id or f"talk-{uuid.uuid4()}"
    return MCPClient(lambda: aws_iam_streamablehttp_client(
        endpoint=STATE["gateway_url"], aws_region=REGION, aws_service="bedrock-agentcore",
        aws_profile=ADMIN_PROFILE,
        headers={"x-amzn-bedrock-agentcore-policy-session-id": sid},
    )), sid


def _short(v, n=900):
    s = v if isinstance(v, str) else json.dumps(v, indent=2, default=str)
    return s if len(s) <= n else s[:n] + f"\n{DIM}... ({len(s) - n} more chars){RESET}"


def show_tool_calls(agent):
    """Print every tool call and result, like the hooks in 'Agents are just loops'."""

    def before(event: BeforeToolCallEvent) -> None:
        tu = event.tool_use
        print(f"\n{CYAN}{BOLD}🔧 Model chose: {tu['name']}{RESET}")
        inp = tu.get("input", {})
        if isinstance(inp, dict) and "code" in inp:      # aws___run_script: show the script it wrote
            print(f"{DIM}   script it wrote:{RESET}")
            for line in inp["code"].splitlines():
                print(f"   {YELLOW}{line}{RESET}")
        else:
            print(f"{DIM}   with inputs:{RESET} {_short(inp, 300)}")
        sys.stdout.flush()

    def after(event: AfterToolCallEvent) -> None:
        r = event.result or {}
        text = " ".join(c.get("text", "") for c in r.get("content", []) if isinstance(c, dict))
        if r.get("status") == "error":
            print(f"   {RED}{BOLD}✗ error:{RESET} {RED}{_short(text, 500)}{RESET}\n")
        else:
            print(f"   {GREEN}✓ result:{RESET} {DIM}{_short(text, 400)}{RESET}\n")
        sys.stdout.flush()

    agent.add_hook(before)
    agent.add_hook(after)
    return agent


def banner(text):
    print(f"\n{BOLD}> {text}{RESET}\n")
