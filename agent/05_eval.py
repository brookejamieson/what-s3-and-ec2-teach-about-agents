"""Slides 32a-32b: an eval for the questions this agent has to get right.

Runs the four read-only questions from the talk, REPEATS times each, once with
the lazy docstring and once with the fixed one. A second model judges each
run's tool calls against the order this agent should use.

Why TrajectoryEvaluator and not ToolSelectionAccuracyEvaluator: tested
2026-10-12, ToolSelectionAccuracy passed the lazy docstring 4/4, because the
judge reads the same vague description the agent did. An expected trajectory
says what "right" means for this agent, so the judge can see the miss.

    python 05_eval.py            # REPEATS=5 -> 20 runs per docstring
    python 05_eval.py 3          # quicker
"""
import json
import sys

from strands import Agent
from strands_evals import Case, Experiment
from strands_evals.evaluators import TrajectoryEvaluator

import catalog_tool
from demo_common import BOLD, RESET, aws_mcp

REPEATS = int(sys.argv[1]) if len(sys.argv) > 1 else 5

# --- slide 32a --------------------------------------------------------------
QUESTIONS = {
    "lambda": ("I'm using a lot of Lambda. What should I know?",
               ["aws___run_script", "search_reinvent_catalog"]),
    "buckets": ("Are any of my buckets public?", ["aws___run_script"]),
    "sessions": ("What's on at re:Invent about S3?", ["search_reinvent_catalog"]),
    "both": ("What's running, and is there a session about it?",
             ["aws___run_script", "search_reinvent_catalog"]),
}
cases = [Case(name=f"{k}-{i}", input=q, expected_trajectory=t)
         for k, (q, t) in QUESTIONS.items() for i in range(REPEATS)]

judge = TrajectoryEvaluator(rubric=(
    "Pass if the agent looked at the user's AWS account (aws___run_script) before relying on "
    "the re:Invent catalog for any question about what the user runs, owns or uses, and used "
    "search_reinvent_catalog for questions about sessions. Repeating a tool is fine. "
    "Fail if it answered a question about the user's own account without looking at the account."))
# ---------------------------------------------------------------------------


def tools_used(agent) -> list:
    return [c["toolUse"]["name"] for m in agent.messages if m["role"] == "assistant"
            for c in m["content"] if "toolUse" in c]


def make_task(catalog):
    def run_agent(case: Case) -> dict:
        agent = Agent(tools=[aws_mcp(), catalog], callback_handler=None)
        response = agent(case.input, limits={"turns": 10})
        return {"output": str(response), "trajectory": tools_used(agent)}
    return run_agent


results = {}
for label, catalog in [("lazy", catalog_tool.search_reinvent_catalog_lazy),
                       ("clear", catalog_tool.search_reinvent_catalog)]:
    results[label] = Experiment(cases=cases, evaluators=[judge]).run_evaluations(make_task(catalog))

# --- slide 32b: summarise ---------------------------------------------------
summary = {}
for label, r in results.items():
    rows = list(zip([c["name"] for c in r.cases], r.test_passes, r.reasons))
    per_q = {}
    for name, ok, _ in rows:
        per_q.setdefault(name.rsplit("-", 1)[0], []).append(bool(ok))
    summary[label] = {"passed": sum(ok for _, ok, _ in rows), "runs": len(rows),
                      "per_question": {q: f"{sum(v)}/{len(v)}" for q, v in per_q.items()},
                      "failed_reasons": [why for _, ok, why in rows if not ok][:4]}
    print(f"\n{BOLD}{label} docstring:{RESET} {summary[label]['passed']}/{summary[label]['runs']} runs passed")
    for q, v in summary[label]["per_question"].items():
        print(f"   {q:9s} {v}")
json.dump(summary, open("eval_results.json", "w"), indent=2, default=str)
print("\nwrote eval_results.json")
