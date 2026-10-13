"""The re:Invent catalog tool, in its lazy (slide 15) and fixed (slide 17) versions.

Both read the session snapshot in S3. Only the docstring differs.
"""
import json
from functools import lru_cache

import boto3
from strands import tool

from demo_common import READONLY_PROFILE, STATE


@lru_cache(maxsize=1)
def _sessions() -> list:
    s3 = boto3.Session(profile_name=READONLY_PROFILE).client("s3")
    body = s3.get_object(Bucket=STATE["buckets"]["catalog"], Key="catalog/reinvent2026.json")["Body"].read()
    return json.loads(body)


def _search(query: str) -> list:
    words = [w for w in query.lower().replace("?", " ").split() if len(w) > 2]
    scored = []
    for s in _sessions():
        hay = " ".join([s["title"], " ".join(s["topics"]), " ".join(s["services"])]).lower()
        score = sum(w in hay for w in words)
        if score:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [{k: s[k] for k in ("code", "title", "level", "date", "time")} for _, s in scored[:5]]


# --- slide 15 ---------------------------------------------------------------
@tool(name="search_reinvent_catalog")
def search_reinvent_catalog_lazy(query: str) -> list:
    """Search for AWS things."""
    return _search(query)
# ---------------------------------------------------------------------------


# --- slide 17 ---------------------------------------------------------------
@tool(name="search_reinvent_catalog")
def search_reinvent_catalog(query: str) -> list:
    """Find re:Invent 2026 sessions about a topic.

    Use this for questions about what to see or learn.
    Returns each session's code, title, level and time.
    Can't see this AWS account. For questions about
    what you're running, check the account first.
    """
    return _search(query)
# ---------------------------------------------------------------------------
