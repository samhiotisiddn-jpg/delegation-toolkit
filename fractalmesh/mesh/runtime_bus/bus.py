"""
fractalmesh/mesh/runtime_bus/bus.py

FractalMesh runtime bus — node discovery, point-to-point dispatch, broadcast.

Usage from other modules:
    from runtime_bus.bus import load_nodes, send_to_node, broadcast
"""

import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Default registry path; override with MESH_NODES_FILE env var.
_DEFAULT_NODES_FILE = os.path.join(
    os.path.expanduser("~"), "ai-mesh", "mesh_nodes.json"
)
MESH_NODES_FILE = os.getenv("MESH_NODES_FILE", _DEFAULT_NODES_FILE)


# ── registry ──────────────────────────────────────────────────────────────────

def load_nodes() -> List[Dict[str, Any]]:
    """Return the list of registered mesh nodes from disk."""
    try:
        with open(MESH_NODES_FILE, "r") as fh:
            return json.load(fh)
    except FileNotFoundError:
        log.warning("mesh_nodes.json not found at %s", MESH_NODES_FILE)
        return []
    except Exception as exc:
        log.error("Failed to load mesh_nodes.json: %s", exc)
        return []


def _get_node(node_id: str) -> Optional[Dict[str, Any]]:
    for node in load_nodes():
        if node.get("id") == node_id:
            return node
    return None


# ── dispatch ──────────────────────────────────────────────────────────────────

def send_to_node(node_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send *payload* to the bridge script of *node_id* via stdin/stdout JSON.

    Returns the parsed JSON response dict, or an ``{"error": ...}`` dict on
    failure.
    """
    node = _get_node(node_id)
    if node is None:
        return {"error": f"node not found: {node_id}"}

    bridge = os.path.expanduser(node.get("bridge_script", ""))
    if not bridge or not os.path.isfile(bridge):
        return {"error": f"bridge script not found: {bridge!r}"}

    try:
        result = subprocess.run(
            ["python3", bridge],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        log.error("Timeout talking to node %s", node_id)
        return {"error": f"timeout contacting {node_id}"}
    except Exception as exc:
        log.error("Subprocess error for node %s: %s", node_id, exc)
        return {"error": str(exc)}

    if result.returncode != 0:
        log.error("Bridge %s exited %d: %s", node_id, result.returncode, result.stderr[:200])
        return {"error": result.stderr.strip() or f"bridge exited {result.returncode}"}

    stdout = result.stdout.strip()
    if not stdout:
        return {"status": "ok", "note": "empty response"}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        log.error("Invalid JSON from %s: %s", node_id, exc)
        return {"error": f"invalid JSON from bridge: {exc}"}


def broadcast(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch *payload* to every registered node (skipping the sender).

    Returns a dict keyed by node_id with each node's response.
    """
    sender = payload.get("from", "")
    responses: Dict[str, Any] = {}
    for node in load_nodes():
        node_id = node.get("id", "")
        if not node_id or node_id == sender:
            continue
        node_payload = dict(payload)
        node_payload["to"] = node_id
        responses[node_id] = send_to_node(node_id, node_payload)
    return responses
