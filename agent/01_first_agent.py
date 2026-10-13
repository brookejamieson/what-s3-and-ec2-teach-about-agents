"""Slides 11-13: the first agent. A model, a loop, and tools from the AWS MCP Server.

    python 01_first_agent.py                 # slide 12
    python 01_first_agent.py --model         # slide 13, the one-line model swap (GPT-5.6 Luna)
    python 01_first_agent.py --limits        # slide 28, turn and token caps
"""
import sys

from strands import Agent
from strands.models import BedrockModel

from demo_common import aws_mcp, banner, show_tool_calls

QUESTION = "What's running in my account?"

aws = aws_mcp()

# --- slide 11 ---------------------------------------------------------------
agent = Agent(tools=[aws])
# ---------------------------------------------------------------------------

if "--model" in sys.argv:
    # --- slide 13 -----------------------------------------------------------
    model = BedrockModel(model_id="global.openai.gpt-5.6-luna")
    agent = Agent(model=model, tools=[aws])
    # -----------------------------------------------------------------------

show_tool_calls(agent)
banner(QUESTION)

if "--limits" in sys.argv:
    # --- slide 28 -----------------------------------------------------------
    result = agent(QUESTION, limits={"turns": 8, "total_tokens": 60000})
    print(f"\nstop_reason: {result.stop_reason}")
    # -----------------------------------------------------------------------
else:
    agent(QUESTION)
print()
