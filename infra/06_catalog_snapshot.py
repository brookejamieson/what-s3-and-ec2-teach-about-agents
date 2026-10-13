"""Step 6: put the re:Invent 2026 session catalog into S3.

Default: upload the curated snapshot in ../data/reinvent2026-curated.json
(34 real sessions copied from the catalog on 2026-10-12, chosen to match
what is planted in the account: idle EC2, S3, Lambda, cost, agents, IAM).

--full: fetch every session from the AWS Events MCP endpoint. re:Invent
requires a signed-in attendee, so set EVENTS_TOKEN to a bearer token from
your re:Invent sign-in first. Refresh shortly before each talk.
"""
import asyncio
import json
import os
import pathlib
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from common import load_state, session

EVENTS_MCP = "https://api.awsevents.com/mcp"
KEY = "catalog/reinvent2026.json"


async def fetch_all():
    headers = {"Authorization": f"Bearer {os.environ['EVENTS_TOKEN']}"}
    out, token, page = [], None, 0
    async with streamablehttp_client(EVENTS_MCP, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            name = next(t for t in tools if t.endswith("ListSessions"))
            while True:
                args = {"eventId": "reinvent2026", "includeAbstracts": False}
                if token:
                    args["nextToken"] = token
                body = json.loads((await s.call_tool(name, args)).content[0].text)
                out.extend(body["items"])
                token = body.get("nextToken")
                page += 1
                print(f"page {page}: {len(out)} sessions", end="\r")
                if not token:
                    break
    print()
    return [{"code": i.get("abbreviation"), "title": i.get("title"),
             "level": (i.get("level") or "")[:3], "type": i.get("type"),
             "topics": i.get("topics", []), "services": i.get("services", []),
             "date": i.get("sessionTime", {}).get("date"), "time": i.get("sessionTime", {}).get("time"),
             "venue": i.get("venue")} for i in out]


if "--full" in sys.argv:
    if "EVENTS_TOKEN" not in os.environ:
        sys.exit("set EVENTS_TOKEN (re:Invent attendee bearer token) for --full")
    sessions = asyncio.run(fetch_all())
else:
    sessions = json.loads((pathlib.Path(__file__).parent.parent / "data" / "reinvent2026-curated.json").read_text())

bucket = load_state()["buckets"]["catalog"]
session().client("s3").put_object(Bucket=bucket, Key=KEY, Body=json.dumps(sessions).encode(),
                                  ContentType="application/json")
print(f"wrote {len(sessions)} sessions to s3://{bucket}/{KEY}")
