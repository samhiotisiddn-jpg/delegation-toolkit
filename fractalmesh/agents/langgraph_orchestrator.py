"""
LangGraph-based Sovereign Orchestrator (local-first).

State graph maps:  sense -> plan -> execute -> review -> (loop or finish)
Tool calling supports web3, trading, rss, outreach, nft, contract, and osint.
"""

import os
import json
import logging
from typing import Any, Callable, TypedDict

log = logging.getLogger("langgraph_orchestrator")

try:
    from langgraph.graph import StateGraph, END
    HAS_LANGGRAPH = True
except Exception as exc:
    log.warning("langgraph not installed: %s", exc)
    StateGraph = None
    END = "__end__"
    HAS_LANGGRAPH = False


class SovereignState(TypedDict, total=False):
    input: str
    context: dict
    plan: list[dict]
    tool_results: list[dict]
    current_step: int
    review: dict
    output: dict
    finished: bool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        from integrations.web3_client import get_balance
        from integrations.trading_engine import get_status
        from integrations.nft_pipeline import create_nft_drop
        from integrations.coingecko import get_prices
        from agents.rss_swarm import ingest_once
        from agents.google_dorker import harvest_all_dorks

        self._tools.update({
            "web3_balance": get_balance,
            "trading_status": get_status,
            "create_nft_drop": create_nft_drop,
            "coingecko_prices": lambda coins="bitcoin,ethereum,solana", vs="aud": get_prices(coins.split(","), vs),
            "rss_ingest": ingest_once,
            "osint_dork": harvest_all_dorks,
        })

    def register(self, name: str, fn: Callable) -> None:
        self._tools[name] = fn

    def call(self, name: str, args: dict) -> dict:
        fn = self._tools.get(name)
        if not fn:
            return {"error": f"tool not found: {name}"}
        try:
            if args:
                return {"tool": name, "result": fn(**args)}
            return {"tool": name, "result": fn()}
        except Exception as exc:
            return {"tool": name, "error": str(exc)}


_REGISTRY = ToolRegistry()


def register_tool(name: str, fn: Callable) -> None:
    _REGISTRY.register(name, fn)


# ── Graph nodes ──────────────────────────────────────────────────────────────

def _sense(state: SovereignState) -> SovereignState:
    """Collect relevant context based on user/agent input."""
    text = state.get("input", "")
    keywords = ["trade", "nft", "crypto", "contract", "osint", "rss", "web3"]
    detected = [k for k in keywords if k in text.lower()]
    state["context"] = {"input": text, "intents": detected, "ts": __import__("time").time()}
    return state


def _plan(state: SovereignState) -> SovereignState:
    """Build a simple deterministic plan from detected intents."""
    intents = state["context"].get("intents", [])
    plan: list[dict] = []
    if "crypto" in intents or "trade" in intents:
        plan.append({"tool": "trading_status"})
        plan.append({"tool": "coingecko_prices", "args": {"coins": "bitcoin,ethereum,solana"}})
    if "nft" in intents:
        plan.append({"tool": "create_nft_drop"})
    if "web3" in intents:
        plan.append({"tool": "web3_balance"})
    if "osint" in intents:
        plan.append({"tool": "osint_dork"})
    if "rss" in intents:
        plan.append({"tool": "rss_ingest"})
    if not plan:
        plan.append({"tool": "coingecko_prices", "args": {"coins": "bitcoin,ethereum"}})
    state["plan"] = plan
    state["current_step"] = 0
    state["tool_results"] = []
    return state


def _execute(state: SovereignState) -> SovereignState:
    """Run the current step and advance."""
    plan = state["plan"]
    step = state["current_step"]
    if step >= len(plan):
        state["finished"] = True
        return state
    action = plan[step]
    result = _REGISTRY.call(action["tool"], action.get("args", {}))
    state["tool_results"].append(result)
    state["current_step"] = step + 1
    return state


def _review(state: SovereignState) -> str:
    """Decide next node path."""
    if state.get("finished") or state["current_step"] >= len(state["plan"]):
        state["output"] = {
            "summary": f"Completed {len(state['plan'])} steps",
            "results": state["tool_results"],
        }
        return END
    return "execute"


# ── Graph builder ────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    if not HAS_LANGGRAPH:
        raise RuntimeError("langgraph not installed; using fallback executor")
    builder = StateGraph(SovereignState)
    builder.add_node("sense", _sense)
    builder.add_node("plan", _plan)
    builder.add_node("execute", _execute)
    builder.add_node("review", _review)
    builder.set_entry_point("sense")
    builder.add_edge("sense", "plan")
    builder.add_edge("plan", "execute")
    builder.add_edge("execute", "review")
    builder.add_conditional_edges("review", lambda s: END if s.get("finished") else ("execute" if s["current_step"] < len(s["plan"]) else END))
    return builder.compile()


def run_sovereign_graph(input_text: str) -> dict:
    """Run the sovereign agent graph on a user prompt and return final output."""
    initial: SovereignState = {"input": input_text}
    if not HAS_LANGGRAPH:
        # Fallback: execute sense/plan/execute directly
        state = _sense(initial)
        state = _plan(state)
        while state["current_step"] < len(state["plan"]):
            state = _execute(state)
        state["output"] = {"summary": f"Completed {len(state['plan'])} steps", "results": state["tool_results"]}
        return state["output"]
    graph = _build_graph()
    final = graph.invoke(initial)
    return final.get("output", final)


def list_tools() -> list[str]:
    return list(_REGISTRY._tools.keys())
