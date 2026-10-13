"""Slides 1 and 30: the phone call as a web page, for the screen behind the handset.

Same agents as 06_phone.py. The page streams the microphone to this server over a
WebSocket; the server runs the BidiAgent and streams the voice, both transcripts and
every step of the account lookup back to the page. Built on the Strands Hotline
pattern.

    python phone_web.py      then open http://127.0.0.1:8766 in Chrome

Local only: binds to 127.0.0.1 with no login, only accepts calls from its own page,
and every call uses this machine's AWS credentials. Don't expose it to a network.
"""
import asyncio
import base64
import contextlib
import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from strands.bidi import BidiAgent
from strands.bidi.types.media import AudioDelta

phone = importlib.import_module("06_phone")  # file name starts with a digit, like the other stages

HERE = Path(__file__).parent
WEB = HERE / "phone_web"
log = logging.getLogger("phone")
INPUT_RATE, OUTPUT_RATE = 16000, 24000  # browser mic in, voice out
PORT = int(os.environ.get("PORT", "8766"))
# The Host header is checked as well as Origin, so a site that rebinds its own
# domain name to 127.0.0.1 (DNS rebinding) still can't open a call.
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
HIDDEN = ("[caller picked up]", "[account answer]")  # messages from the line, not the caller

# One account agent for the whole server, built before the first call: starting the
# AWS MCP proxy takes about 10 seconds, and on stage the phone should pick up at once.
STEP: dict[str, Any] = {"fn": None}


async def _report(step):
    if STEP["fn"]:
        await STEP["fn"](step)

ACCOUNT = phone.make_account(_report)


class Call:
    """One browser call: the input and output streams BidiAgent.run() drives."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws, self.inbox, self.lock = ws, asyncio.Queue(), asyncio.Lock()

    async def send_json(self, data: dict[str, Any]) -> None:
        if self.ws.client_state == WebSocketState.CONNECTED:
            async with self.lock:
                with contextlib.suppress(Exception):
                    await self.ws.send_text(json.dumps(data))

    async def send_audio(self, pcm: bytes) -> None:
        if self.ws.client_state == WebSocketState.CONNECTED:
            async with self.lock:
                with contextlib.suppress(Exception):
                    await self.ws.send_bytes(pcm)

    async def read_browser(self) -> None:
        try:
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes"):
                    await self.inbox.put(AudioDelta(format="pcm", source={"bytes": message["bytes"]}))
                elif message.get("text"):
                    data = json.loads(message["text"])
                    if data.get("type") == "hangup":
                        break
                    if data.get("type") == "text" and str(data.get("text", "")).strip():
                        await self.inbox.put(str(data["text"])[:2000])
        except WebSocketDisconnect:
            pass
        await self.inbox.put(None)

    class Input:
        def __init__(self, call): self.call = call
        async def start(self, agent): return
        async def stop(self): return

        async def __call__(self):
            item = await self.call.inbox.get()
            if item is None:  # caller hung up; call_endpoint cancels run()
                await asyncio.Event().wait()
            return item

    class Output:
        def __init__(self, call): self.call = call
        async def start(self, agent): return
        async def stop(self): return

        async def __call__(self, event):
            kind, c = event.get("type"), self.call
            if kind == "bidi_audio_delta":
                await c.send_audio(base64.b64decode(event["audio"]))
            elif kind == "bidi_barge_in":
                await c.send_json({"type": "barge_in"})
            elif kind in ("bidi_transcript_delta", "bidi_transcript_block"):
                text = event["delta"] if kind == "bidi_transcript_delta" else event["transcript"]
                if any(h in text for h in HIDDEN):
                    return
                await c.send_json({"type": "transcript_delta" if kind.endswith("delta") else "transcript_done",
                                   "role": event["role"], "id": event["content_id"], "text": text})
            elif kind == "bidi_connection_restart":
                await c.send_json({"type": "status", "text": "reconnecting"})


async def index(_request):
    return FileResponse(WEB / "index.html")


async def call_endpoint(ws: WebSocket) -> None:
    # Only pages served by this app, so another site open in the browser can't
    # place calls on this machine's AWS account.
    host = ws.headers.get("host", "")
    if host not in ALLOWED_HOSTS or ws.headers.get("origin", "") != f"http://{host}":
        await ws.close(code=1008)
        return
    await ws.accept()
    call = Call(ws)

    async def on_step(step):
        await call.send_json({"type": "lookup", **step})

    STEP["fn"] = on_step          # the shared agent's hooks report to this call's page
    ACCOUNT.messages.clear()      # each call starts a fresh conversation

    agent = BidiAgent(
        model=phone.voice_model(audio={"input": {"sample_rate": INPUT_RATE},
                                       "output": {"sample_rate": OUTPUT_RATE}}),
        tools=[phone.make_ask_my_account(call.inbox.put, on_step, ACCOUNT), phone.end_call],
        system_prompt=phone.PHONE_PROMPT,
    )
    reader = asyncio.create_task(call.read_browser())
    await call.send_json({"type": "status", "text": "connected"})
    await call.inbox.put("[caller picked up]")  # Nova Sonic only speaks after it hears something
    run = asyncio.create_task(agent.run(inputs=[Call.Input(call)], outputs=[Call.Output(call)]))
    try:
        await asyncio.wait({run, reader}, return_when=asyncio.FIRST_COMPLETED)
        if not run.done():
            run.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run
    except Exception as error:  # show model errors (credentials, filters) on the page
        log.exception("call failed")
        await call.send_json({"type": "error", "text": str(error)[-300:]})
    finally:
        reader.cancel()
        await call.send_json({"type": "status", "text": "ended"})
        if ws.client_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await ws.close()


app = Starlette(routes=[
    Route("/", index),
    WebSocketRoute("/call", call_endpoint),
    Mount("/", StaticFiles(directory=WEB)),
])

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="127.0.0.1", port=PORT)
