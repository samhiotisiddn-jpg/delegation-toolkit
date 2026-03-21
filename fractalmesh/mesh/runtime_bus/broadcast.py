"""
fractalmesh/mesh/runtime_bus/broadcast.py

Convenience wrapper around bus.broadcast() for typed callers.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .bus import broadcast as _bus_broadcast


def broadcast_message(
    session_id: str,
    from_node: str,
    message: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Broadcast *message* from *from_node* to all registered mesh nodes.

    Returns a dict of ``{node_id: response}`` from every node reached.
    """
    payload: Dict[str, Any] = {
        "session_id": session_id,
        "from": from_node,
        "to": "broadcast",
        "message": message,
        "meta": meta or {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "broadcast": True,
        },
    }
    return _bus_broadcast(payload)
