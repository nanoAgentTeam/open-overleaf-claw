"""WebUI Chat WebSocket endpoint — bridges browser ↔ MessageBus ↔ AgentLoop."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse
from loguru import logger

from bus.events import InboundMessage, OutboundMessage

if TYPE_CHECKING:
    from bus.queue import MessageBus

chat_router = APIRouter()

# Will be injected by gateway_server at import time
_bus: MessageBus | None = None
_agent_loop = None  # AgentLoop reference for history access

CHANNEL = "webui"
CHAT_ID = "webui_default"
SENDER_ID = "webui_user"


def init_chat_api(bus: MessageBus, agent_loop=None) -> None:
    """Called once from gateway_server to inject the shared MessageBus."""
    global _bus, _agent_loop
    _bus = bus
    _agent_loop = agent_loop


@chat_router.get("/api/chat/commands")
async def list_commands():
    """Return visible (non-hidden) commands for UI autocomplete."""
    try:
        from config.registry import ConfigRegistry
        registry = ConfigRegistry()
        cmds = registry.get_visible_commands()
        return [
            {
                "name": c.name,
                "description": c.description,
                "args_usage": c.args_usage,
                "requires_args": c.requires_args,
            }
            for c in cmds.values()
        ]
    except Exception:
        return []


@chat_router.get("/api/chat/history")
async def get_history(limit: int = 50):
    """Return recent chat history for the webui session."""
    if not _agent_loop:
        return []
    try:
        history = await _agent_loop.history_logger.get_recent_history(
            chat_id=CHAT_ID, limit=limit,
        )
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in history
            if msg.get("content")
        ]
    except Exception:
        return []


@chat_router.get("/api/chat/file")
async def download_file(path: str):
    """Serve a workspace file for download."""
    p = Path(path)
    if not p.is_absolute() or not p.exists() or not p.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")
    response = FileResponse(p, filename=p.name)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@chat_router.post("/api/chat/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file and return its path for use in chat messages."""
    if not _agent_loop:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Agent not ready")
    upload_dir = Path(_agent_loop.workspace) / ".uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename
    # Avoid overwriting
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        i = 1
        while dest.exists():
            dest = upload_dir / f"{stem}_{i}{suffix}"
            i += 1
    content = await file.read()
    dest.write_bytes(content)
    return {"path": str(dest), "name": dest.name, "size": len(content)}


@chat_router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    if _bus is None:
        await websocket.close(code=1011, reason="MessageBus not initialised")
        return

    outbound_queue: asyncio.Queue[OutboundMessage] = asyncio.Queue()
    closed = False

    async def _on_outbound(msg: OutboundMessage) -> None:
        """Subscriber callback — enqueue outbound messages for this client."""
        if closed:
            return
        await outbound_queue.put(msg)

    _bus.subscribe_outbound(CHANNEL, _on_outbound)
    logger.info("WebUI chat client connected")

    async def _sender():
        """Forward queued outbound messages to the browser."""
        nonlocal closed
        try:
            while not closed:
                try:
                    msg = await asyncio.wait_for(outbound_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if msg.is_chunk:
                    payload = {
                        "type": "chunk",
                        "content": msg.content,
                        "stream_id": msg.stream_id or "main",
                        "new_message": msg.new_message,
                    }
                else:
                    payload = {
                        "type": "message",
                        "role": "assistant",
                        "content": msg.content,
                        "is_notification": msg.is_notification,
                        "media": msg.media or [],
                    }
                try:
                    await websocket.send_text(json.dumps(payload, ensure_ascii=False))
                except Exception:
                    closed = True
                    return
        except asyncio.CancelledError:
            pass

    sender_task = asyncio.create_task(_sender())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")
            content = (data.get("content") or "").strip()
            if not content:
                continue

            if msg_type == "message":
                media = data.get("media") or []
                inbound = InboundMessage(
                    channel=CHANNEL,
                    sender_id=SENDER_ID,
                    chat_id=CHAT_ID,
                    content=content,
                    media=media,
                )
                await _bus.publish_inbound(inbound)
                # Echo back to confirm receipt
                echo = {"type": "message", "role": "user", "content": content, "media": media}
                await websocket.send_text(json.dumps(echo, ensure_ascii=False))
                # Notify busy
                await websocket.send_text(json.dumps({"type": "status", "busy": True}))

    except (WebSocketDisconnect, Exception) as exc:
        if not isinstance(exc, WebSocketDisconnect):
            logger.debug(f"WebUI chat ws error: {exc}")
    finally:
        closed = True
        _bus.unsubscribe_outbound(CHANNEL, _on_outbound)
        sender_task.cancel()
        logger.info("WebUI chat client disconnected")
