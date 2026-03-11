import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_subscribers: list[asyncio.Queue] = []
_lock = asyncio.Lock()


async def subscribe() -> asyncio.Queue:
    """Subscribe to all events. Returns a queue for reading."""
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    async with _lock:
        _subscribers.append(q)
    return q


async def unsubscribe(q: asyncio.Queue) -> None:
    """Unsubscribe (call when closing a WS connection)."""
    async with _lock:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


async def emit(event_type: str, payload: dict[str, Any] | None = None) -> None:
    """
      Publish an event to all subscribers.

      event_type — a string like "user.created", "user.traffic_exceeded",
                  "user.deactivated", "host.added", ...
      payload    — an arbitrary dict with event data.
    """
    message = json.dumps({"event": event_type, "data": payload or {}})
    async with _lock:
        dead: list[asyncio.Queue] = []
        for q in _subscribers:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("event queue full for a subscriber, dropping event '%s'", event_type)
            except Exception as exc:
                logger.error("failed to deliver event '%s': %s", event_type, exc)
                dead.append(q)
        for q in dead:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass
