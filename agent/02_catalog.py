"""Slides 15-18: a tool of my own, what the model sees, the wrong pick, the fix.

    python 02_catalog.py --spec           # slide 15a: print what the model gets (lazy docstring)
    python 02_catalog.py --spec --clear   # after slide 17: the same print with the fixed docstring
    python 02_catalog.py --lazy           # slide 16: the Lambda question, lazy docstring
    python 02_catalog.py                  # slide 18: same question, fixed docstring
"""
import json
import sys

from strands import Agent

from catalog_tool import search_reinvent_catalog, search_reinvent_catalog_lazy
from demo_common import BOLD, DIM, RESET, aws_mcp, banner, show_tool_calls

QUESTION = "I'm using a lot of Lambda. What should I know?"
lazy = "--lazy" in sys.argv or ("--spec" in sys.argv and "--clear" not in sys.argv)
catalog = search_reinvent_catalog_lazy if lazy else search_reinvent_catalog
aws = aws_mcp()

if "--spec" in sys.argv:
    # --- slide 15a ---------------------------------------------------------
    print(json.dumps(catalog.tool_spec, indent=1))
    # ----------------------------------------------------------------------
    with aws:
        run = next(t for t in aws.list_tools_sync() if t.tool_name == "aws___run_script")
        print(f"\n{BOLD}For comparison, the start of aws___run_script's description "
              f"({len(run.tool_spec['description'])} characters):{RESET}")
        print(DIM + run.tool_spec["description"][:700] + " ..." + RESET)
        if "--full" in sys.argv:
            print(run.tool_spec["description"])
    sys.exit()

# --- slide 15 ---------------------------------------------------------------
agent = Agent(tools=[aws, catalog])
# ---------------------------------------------------------------------------

show_tool_calls(agent)
banner(QUESTION)
agent(QUESTION)
print()
