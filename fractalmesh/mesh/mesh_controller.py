#!/usr/bin/env python3
"""
fractalmesh/mesh/mesh_controller.py

FractalMesh CLI controller — send messages to one node or broadcast to all.

Usage:
    python3 mesh_controller.py --to xai-grok --message "hello"
    python3 mesh_controller.py --broadcast --message "activate all nodes"
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

# Allow running from any directory
sys.path.insert(0, os.path.dirname(__file__))
from runtime_bus.bus import broadcast, send_to_node


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FractalMesh CLI controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 mesh_controller.py --to xai-grok --message "summarize income streams"
  python3 mesh_controller.py --broadcast --message "status check"
        """,
    )
    parser.add_argument("--to", help="Target node ID")
    parser.add_argument("--broadcast", action="store_true", help="Send to all nodes")
    parser.add_argument("--message", required=True, help="Message text")
    parser.add_argument("--session-id", default=None, help="Optional session ID")
    args = parser.parse_args()

    if not args.to and not args.broadcast:
        parser.error("Specify --to <node_id> or --broadcast")

    session_id = args.session_id or str(uuid.uuid4())
    payload = {
        "session_id": session_id,
        "from": "mesh_controller",
        "to": args.to if args.to else "broadcast",
        "message": args.message,
        "meta": {
            "timestamp": _now(),
            "source": "cli",
        },
    }

    if args.broadcast:
        result = broadcast(payload)
    else:
        result = send_to_node(args.to, payload)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
