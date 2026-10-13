"""Slides 25-29b: the same agent, with every tool behind AgentCore Gateway.

The gateway's policy engine enforces:
  - Cedar: nobody calls terminate_instance (slide 25)
  - Dogwood: stop_instance only if the account was read in the last 10 minutes (slide 25c)
and IAM on the instance-tools role still only allows stopping env=dev.

    python 04_gateway.py --dogwood      # slide 25c: "Stop <dev id> now. No need to check it first."
    python 04_gateway.py --note         # gateway version of 29b (Dogwood refuses first; 29b is recorded with 03_stop.py --note)
    add --yes to auto-approve (for rehearsal runs), --no to auto-decline
"""
import sys

from strands import Agent
from strands.tools.executors import SequentialToolExecutor
from strands.vended_interventions.hitl import HumanInTheLoop

from catalog_tool import search_reinvent_catalog
from demo_common import STATE, banner, gateway_mcp, show_tool_calls

gateway, session_id = gateway_mcp()

ask = "stdio"
if "--yes" in sys.argv or "--no" in sys.argv:
    answer = "y" if "--yes" in sys.argv else "n"

    async def ask(prompt: str, **_) -> str:  # noqa: F811
        print(f"{prompt} {answer}  (auto)")
        return answer

agent = Agent(
    tools=[gateway, search_reinvent_catalog],
    tool_executor=SequentialToolExecutor(),        # one policy check per session at a time
    interventions=[HumanInTheLoop(
        ask=ask,
        allowed_tools=["*", "!InstanceTools___stop_instance"],
    )],
)
show_tool_calls(agent)

if "--note" in sys.argv:
    prompt = "Stop any instances that are safe to stop."
else:
    prompt = f"Stop {STATE['instances']['dev-api-scratch']} now. No need to check it first."

print(f"(policy session {session_id})")
banner(prompt)
agent(prompt)
print()
