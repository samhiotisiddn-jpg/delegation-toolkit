#!/usr/bin/env python3
"""
FractalMesh Sovereign Orchestrator — Mode B
===========================================
Pure supervisor / control plane.

Responsibilities
----------------
- Load agent definitions from registry.yaml
- Build a dependency graph (DAG) and compute safe start / restart order
- Supervise every agent: process liveness, port binding, heartbeat, log
  freshness, and resource usage
- Perform soft or cascade restarts based on failure mode
- Expose a REST control plane on http://127.0.0.1:9999/
- Write structured logs to logs/orchestrator.log and logs/supervisor.log

What this orchestrator does NOT do (Mode B contract)
-----------------------------------------------------
- Mutate / patch agent source code
- Pull remote repositories or apply external updates
- Evolve strategies or generate new agents
- Write or modify environment variable values

Usage
-----
    python3 orchestrator.py [--registry /path/to/registry.yaml]

Dependencies (all optional—graceful degradation if absent)
-----------
    pip install pyyaml requests psutil
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Optional heavy deps ────────────────────────────────────────────────────────
try:
    import yaml as _yaml  # type: ignore

    def _yaml_load(stream):
        return _yaml.safe_load(stream)
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import psutil as _psutil  # type: ignore
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests as _requests  # type: ignore
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DEFAULT_REGISTRY = BASE_DIR / "registry.yaml"
STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
GRAPH_PATH = BASE_DIR / "dependency_graph.json"

API_HOST = "127.0.0.1"
API_PORT = 9999

SUPERVISOR_INTERVAL_S = 5        # seconds between full health sweeps
HEARTBEAT_TIMEOUT_S = 30         # seconds before a silent heartbeat triggers restart
LOG_STALE_THRESHOLD_S = 60       # seconds before a non-updating log triggers restart
LOG_TAIL_LINES = 50              # default lines returned by /logs/<name>
CPU_THRESHOLD_PCT = 90.0
MEM_THRESHOLD_PCT = 90.0
FD_THRESHOLD = 1000
CASCADE_INTER_AGENT_DELAY_S = 0.5

# ── Logging bootstrap ─────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=_fmt,
    handlers=[
        logging.FileHandler(LOG_DIR / "orchestrator.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
orch_log = logging.getLogger("orchestrator")
sup_log = logging.getLogger("supervisor")


# ═══════════════════════════════════════════════════════════════════════════════
# Registry loader
# ═══════════════════════════════════════════════════════════════════════════════

def load_registry(path: Path) -> List[Dict]:
    """
    Parse registry.yaml and return a list of agent dicts.

    Falls back to an empty list with a warning when:
    - the file does not exist
    - PyYAML is not installed (no YAML parser available)
    """
    if not path.exists():
        orch_log.error("Registry file not found: %s", path)
        return []
    if not HAS_YAML:
        orch_log.error(
            "PyYAML is not installed; cannot parse registry.yaml. "
            "Install it with: pip install pyyaml"
        )
        return []
    with open(path) as fh:
        data = _yaml_load(fh) or {}
    agents = data.get("agents", [])
    orch_log.info("Loaded %d agent(s) from %s", len(agents), path)
    return agents


# ═══════════════════════════════════════════════════════════════════════════════
# Dependency graph
# ═══════════════════════════════════════════════════════════════════════════════

class DependencyGraph:
    """
    Directed Acyclic Graph of agent dependencies.

    Edges are directed FROM dependency TO dependent:
        nextupdate → royce → meshmax → ultra → evolve → converge → local

    Provides:
    - topological start order  (deps before dependents)
    - cascade restart order    (failed agent + all downstream dependents)
    - human-readable dict / JSON export
    """

    def __init__(self, agents: List[Dict]) -> None:
        self._agents = {a["name"]: a for a in agents}
        self._deps: Dict[str, List[str]] = {}          # name → its dependencies
        self._rdeps: Dict[str, List[str]] = defaultdict(list)  # dep → its dependents
        self._build()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self) -> None:
        for agent in self._agents.values():
            name = agent["name"]
            deps = agent.get("depends_on", [])
            self._deps[name] = deps
            for dep in deps:
                self._rdeps[dep].append(name)

        self._persist()

    def _persist(self) -> None:
        payload = {
            "agents": list(self._agents.keys()),
            "edges": self._deps,
            "reverse_edges": {k: v for k, v in self._rdeps.items()},
            "topological_start_order": self.topological_start_order(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with open(GRAPH_PATH, "w") as fh:
                json.dump(payload, fh, indent=2)
        except OSError as exc:
            orch_log.warning("Could not persist dependency graph: %s", exc)

    # ── Queries ───────────────────────────────────────────────────────────────

    def dependencies_of(self, name: str) -> List[str]:
        return list(self._deps.get(name, []))

    def dependents_of(self, name: str) -> List[str]:
        return list(self._rdeps.get(name, []))

    def topological_start_order(self) -> List[str]:
        """Return agent names with dependencies before dependents (Kahn's algorithm)."""
        in_degree = {n: 0 for n in self._agents}
        for deps in self._deps.values():
            for dep in deps:
                if dep in in_degree:
                    pass  # dep is the source; increment target's in-degree
        # Build correctly
        in_degree = {n: 0 for n in self._agents}
        for name, deps in self._deps.items():
            for dep in deps:
                in_degree[name] = in_degree.get(name, 0) + 1

        queue = [n for n, deg in in_degree.items() if deg == 0]
        order: List[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for dependent in self._rdeps.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        # Append any remaining (handles cycles gracefully)
        for n in self._agents:
            if n not in order:
                order.append(n)
        return order

    def cascade_restart_order(self, failed: str) -> List[str]:
        """
        BFS from *failed* through the reverse graph to collect all
        downstream dependents that must also be restarted.

        Returns the ordered list starting with *failed* itself.
        """
        visited: set = {failed}
        result: List[str] = [failed]
        queue: List[str] = list(self._rdeps.get(failed, []))

        while queue:
            agent = queue.pop(0)
            if agent not in visited:
                visited.add(agent)
                result.append(agent)
                queue.extend(self._rdeps.get(agent, []))
        return result

    def as_dict(self) -> Dict:
        return {
            "agents": list(self._agents.keys()),
            "edges": self._deps,
            "reverse_edges": {k: list(v) for k, v in self._rdeps.items()},
            "topological_start_order": self.topological_start_order(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Process manager
# ═══════════════════════════════════════════════════════════════════════════════

class ProcessManager:
    """
    Launches, tracks, and terminates agent subprocesses.

    State is kept in memory and flushed to state/pids.json after each change
    so the orchestrator can recover across restarts.
    """

    _PID_FILE = STATE_DIR / "pids.json"

    def __init__(self) -> None:
        self._procs: Dict[str, subprocess.Popen] = {}
        self._started_at: Dict[str, float] = {}
        self._restart_count: Dict[str, int] = defaultdict(int)
        self._last_restart_ts: Dict[str, Optional[str]] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, agent: Dict) -> bool:
        """Launch the agent process. Returns True on success."""
        name = agent["name"]
        script = agent.get("script", "")

        if not script:
            orch_log.error("[%s] No script defined in registry.", name)
            return False
        if not Path(script).exists():
            orch_log.error("[%s] Script not found: %s", name, script)
            return False

        env = os.environ.copy()
        for key in agent.get("env", []):
            val = os.environ.get(key)
            if val is not None:
                env[key] = val

        try:
            proc = subprocess.Popen(
                [sys.executable, script],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            orch_log.error("[%s] Failed to launch: %s", name, exc)
            return False

        self._procs[name] = proc
        self._started_at[name] = time.monotonic()
        self._last_restart_ts[name] = datetime.now(timezone.utc).isoformat()
        self._flush()
        orch_log.info("[%s] Started — PID %d", name, proc.pid)
        return True

    def stop(self, name: str) -> bool:
        """Terminate the agent process gracefully (SIGTERM → SIGKILL)."""
        proc = self._procs.pop(name, None)
        if proc is None:
            return False
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            except OSError:
                pass
        self._flush()
        orch_log.info("[%s] Stopped", name)
        return True

    def restart(self, name: str, agent: Dict) -> bool:
        """Stop then start. Returns True if the new process launched."""
        self.stop(name)
        time.sleep(1)
        self._restart_count[name] += 1
        return self.start(agent)

    def is_running(self, name: str) -> bool:
        proc = self._procs.get(name)
        return proc is not None and proc.poll() is None

    def pid(self, name: str) -> Optional[int]:
        proc = self._procs.get(name)
        if proc and proc.poll() is None:
            return proc.pid
        return None

    def uptime_s(self, name: str) -> Optional[float]:
        t = self._started_at.get(name)
        return round(time.monotonic() - t, 1) if t else None

    def restart_count(self, name: str) -> int:
        return self._restart_count[name]

    def last_restart_ts(self, name: str) -> Optional[str]:
        return self._last_restart_ts.get(name)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _flush(self) -> None:
        data = {}
        for name, proc in self._procs.items():
            if proc.poll() is None:
                data[name] = {
                    "pid": proc.pid,
                    "restarts": self._restart_count[name],
                    "last_restart": self._last_restart_ts.get(name),
                }
        try:
            with open(self._PID_FILE, "w") as fh:
                json.dump(data, fh, indent=2)
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# Health checker
# ═══════════════════════════════════════════════════════════════════════════════

class HealthResult:
    __slots__ = (
        "process_ok", "port_ok", "heartbeat_ok",
        "log_ok", "resource_ok",
        "cpu_pct", "mem_pct", "fd_count",
        "failure_reason",
    )

    def __init__(self) -> None:
        self.process_ok = False
        self.port_ok = False
        self.heartbeat_ok = True   # assumed OK when not configured
        self.log_ok = True         # assumed OK when not configured
        self.resource_ok = True
        self.cpu_pct: float = 0.0
        self.mem_pct: float = 0.0
        self.fd_count: int = 0
        self.failure_reason: str = ""

    @property
    def healthy(self) -> bool:
        return self.process_ok and self.port_ok

    @property
    def soft_restart_needed(self) -> bool:
        return (
            self.healthy
            and (not self.heartbeat_ok or not self.log_ok or not self.resource_ok)
        )

    def to_dict(self) -> Dict:
        return {
            "healthy": self.healthy,
            "process_ok": self.process_ok,
            "port_ok": self.port_ok,
            "heartbeat_ok": self.heartbeat_ok,
            "log_ok": self.log_ok,
            "resource_ok": self.resource_ok,
            "cpu_pct": self.cpu_pct,
            "mem_pct": self.mem_pct,
            "fd_count": self.fd_count,
            "failure_reason": self.failure_reason,
        }


class HealthChecker:
    """Performs all health checks for a single agent."""

    def __init__(self, proc_mgr: ProcessManager) -> None:
        self._pm = proc_mgr
        # Records when we last got a successful heartbeat response
        self._last_heartbeat_ok: Dict[str, float] = {}

    def check(self, agent: Dict) -> HealthResult:
        r = HealthResult()
        name = agent["name"]

        # ── 1. Process liveness ───────────────────────────────────────────────
        r.process_ok = self._pm.is_running(name)
        if not r.process_ok:
            r.failure_reason = "process_dead"
            return r

        # ── 2. Port binding ───────────────────────────────────────────────────
        port = agent.get("port")
        if port:
            r.port_ok = _tcp_open("127.0.0.1", int(port))
            if not r.port_ok:
                r.failure_reason = "port_closed"
        else:
            r.port_ok = True   # not required for this agent

        # ── 3. Heartbeat (HTTP GET) ───────────────────────────────────────────
        hb_path = agent.get("heartbeat")
        if hb_path and port:
            url = f"http://127.0.0.1:{port}{hb_path}"
            ok = self._http_heartbeat(url, name)
            r.heartbeat_ok = ok
            if not ok:
                r.failure_reason = r.failure_reason or "heartbeat_timeout"
        # else: leave heartbeat_ok = True (not configured)

        # ── 4. Log freshness ─────────────────────────────────────────────────
        log_path = agent.get("log")
        if log_path:
            r.log_ok = _log_is_fresh(log_path)
            if not r.log_ok:
                r.failure_reason = r.failure_reason or "log_stale"
        # else: leave log_ok = True (not configured)

        # ── 5. Resource usage ─────────────────────────────────────────────────
        pid = self._pm.pid(name)
        if pid and HAS_PSUTIL:
            self._check_resources(pid, r)

        return r

    def _http_heartbeat(self, url: str, name: str) -> bool:
        if not HAS_REQUESTS:
            return True   # cannot check; assume OK
        try:
            resp = _requests.get(url, timeout=5)
            ok = resp.status_code < 500
            if ok:
                self._last_heartbeat_ok[name] = time.monotonic()
            return ok
        except Exception:
            last = self._last_heartbeat_ok.get(name)
            if last is None or (time.monotonic() - last) > HEARTBEAT_TIMEOUT_S:
                return False
            return True   # still within grace window

    @staticmethod
    def _check_resources(pid: int, r: HealthResult) -> None:
        try:
            proc = _psutil.Process(pid)
            r.cpu_pct = proc.cpu_percent(interval=0.1)
            r.mem_pct = proc.memory_percent()
            try:
                r.fd_count = proc.num_fds()
            except (AttributeError, OSError):
                pass
            if (
                r.cpu_pct > CPU_THRESHOLD_PCT
                or r.mem_pct > MEM_THRESHOLD_PCT
                or r.fd_count > FD_THRESHOLD
            ):
                r.resource_ok = False
                r.failure_reason = r.failure_reason or "resource_exceeded"
        except _psutil.NoSuchProcess:
            r.process_ok = False
            r.failure_reason = "process_vanished"


def _tcp_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _log_is_fresh(log_path: str) -> bool:
    p = Path(log_path)
    if not p.exists():
        return True   # has not been created yet — that is OK
    age = time.time() - p.stat().st_mtime
    return age < LOG_STALE_THRESHOLD_S


# ═══════════════════════════════════════════════════════════════════════════════
# Supervisor
# ═══════════════════════════════════════════════════════════════════════════════

class Supervisor:
    """
    Core supervisor loop and high-level restart coordinator.

    The loop runs in its own thread; all public methods are thread-safe via
    a shared lock.
    """

    def __init__(
        self,
        agents: List[Dict],
        graph: DependencyGraph,
        proc_mgr: ProcessManager,
        health_checker: HealthChecker,
    ) -> None:
        self._agents: Dict[str, Dict] = {a["name"]: a for a in agents}
        self._graph = graph
        self._pm = proc_mgr
        self._hc = health_checker
        self._running = False
        self._lock = threading.Lock()

        self._health: Dict[str, HealthResult] = {}     # latest health per agent
        self._events: deque = deque(maxlen=500)         # audit event ring buffer

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start_all(self) -> None:
        """Start agents in dependency order."""
        for name in self._graph.topological_start_order():
            agent = self._agents.get(name)
            if agent and not self._pm.is_running(name):
                if self._pm.start(agent):
                    time.sleep(CASCADE_INTER_AGENT_DELAY_S)

    def stop_all(self) -> None:
        """Stop agents in reverse dependency order (dependents first)."""
        for name in reversed(self._graph.topological_start_order()):
            if self._pm.is_running(name):
                self._pm.stop(name)

    def start_agent(self, name: str) -> bool:
        agent = self._agents.get(name)
        return self._pm.start(agent) if agent else False

    def stop_agent(self, name: str) -> bool:
        return self._pm.stop(name)

    def restart_agent(self, name: str) -> bool:
        agent = self._agents.get(name)
        if not agent:
            return False
        self._emit("manual_restart", name, "operator-requested restart")
        return self._pm.restart(name, agent)

    # ── Supervisor loop ───────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        orch_log.info("Supervisor loop started (interval=%ds)", SUPERVISOR_INTERVAL_S)
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                orch_log.exception("Supervisor tick error: %s", exc)
            time.sleep(SUPERVISOR_INTERVAL_S)

    def stop(self) -> None:
        self._running = False

    def _tick(self) -> None:
        for name, agent in self._agents.items():
            result = self._hc.check(agent)
            with self._lock:
                self._health[name] = result

            if not result.healthy:
                self._handle_hard_failure(name, agent, result)
            elif result.soft_restart_needed:
                self._soft_restart(name, agent, result.failure_reason)

    # ── Restart logic ─────────────────────────────────────────────────────────

    def _handle_hard_failure(
        self, name: str, agent: Dict, result: HealthResult
    ) -> None:
        policy = agent.get("restart", "always")
        if policy != "always":
            sup_log.info("[%s] Restart policy is '%s'; skipping.", name, policy)
            return

        reason = result.failure_reason
        sup_log.warning("[%s] Hard failure: %s", name, reason)
        self._emit("hard_failure", name, reason)

        if reason in ("process_dead", "port_closed", "process_vanished"):
            self._cascade_restart(name)
        else:
            # Script/env validation failure — hard restart single agent
            self._hard_restart_single(name, agent, reason)

    def _soft_restart(self, name: str, agent: Dict, reason: str) -> None:
        sup_log.info("[%s] Soft restart triggered: %s", name, reason)
        self._emit("soft_restart", name, reason)
        self._pm.restart(name, agent)

    def _hard_restart_single(
        self, name: str, agent: Dict, reason: str
    ) -> None:
        sup_log.warning("[%s] Hard restart: %s", name, reason)
        self._emit("hard_restart", name, reason)
        self._pm.stop(name)
        time.sleep(1)
        self._pm.start(agent)

    def _cascade_restart(self, failed: str) -> None:
        """
        When a foundational agent dies:
        1. Stop all downstream dependents.
        2. Restart in dependency order (deps before dependents).
        """
        cascade = self._graph.cascade_restart_order(failed)
        sup_log.warning(
            "Cascade restart — root: [%s] — sequence: %s",
            failed,
            " → ".join(cascade),
        )
        self._emit("cascade_restart", failed, f"sequence: {cascade}")

        # Stop in reverse order (outermost dependents first)
        for name in reversed(cascade):
            if self._pm.is_running(name):
                self._pm.stop(name)
        time.sleep(1)

        # Restart in forward order (deps first)
        for name in cascade:
            agent = self._agents.get(name)
            if not agent:
                continue
            ok = self._pm.start(agent)
            if not ok:
                sup_log.error("[%s] Failed to restart during cascade.", name)
            time.sleep(CASCADE_INTER_AGENT_DELAY_S)

    # ── Event log ─────────────────────────────────────────────────────────────

    def _emit(self, event_type: str, agent: str, detail: str) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "agent": agent,
            "detail": detail,
        }
        self._events.appendleft(entry)
        try:
            with open(LOG_DIR / "supervisor.log", "a") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    # ── Introspection (called from API thread) ────────────────────────────────

    def health_snapshot(self) -> Dict[str, Dict]:
        with self._lock:
            return {name: r.to_dict() for name, r in self._health.items()}

    def agent_detail(self, name: str) -> Optional[Dict]:
        agent = self._agents.get(name)
        if not agent:
            return None
        with self._lock:
            health = self._health.get(name, HealthResult()).to_dict()
        return {
            "name": name,
            "script": agent.get("script"),
            "port": agent.get("port"),
            "heartbeat": agent.get("heartbeat"),
            "log": agent.get("log"),
            "restart_policy": agent.get("restart", "always"),
            "depends_on": agent.get("depends_on", []),
            "dependents": self._graph.dependents_of(name),
            "env_vars": agent.get("env", []),
            "pid": self._pm.pid(name),
            "uptime_s": self._pm.uptime_s(name),
            "restart_count": self._pm.restart_count(name),
            "last_restart": self._pm.last_restart_ts(name),
            "health": health,
        }

    def log_tail(self, name: str, lines: int = LOG_TAIL_LINES) -> List[str]:
        agent = self._agents.get(name)
        if not agent:
            return []
        log_path = agent.get("log")
        if not log_path:
            return []
        p = Path(log_path)
        if not p.exists():
            return []
        try:
            text = p.read_text(errors="replace").splitlines()
            return text[-lines:]
        except OSError as exc:
            return [f"[error reading log: {exc}]"]

    def recent_events(self, n: int = 20) -> List[Dict]:
        return list(self._events)[:n]


# ═══════════════════════════════════════════════════════════════════════════════
# REST control-plane API (pure stdlib — no Flask dependency)
# ═══════════════════════════════════════════════════════════════════════════════

# Module-level reference set by main() so the handler can reach it
_supervisor: Optional[Supervisor] = None


class _APIHandler(BaseHTTPRequestHandler):
    """
    Minimal HTTP/1.1 handler for the orchestrator control plane.
    Bound to 127.0.0.1 only.

    Endpoints
    ---------
    GET  /status             Full mesh status summary
    GET  /agents             All agents + condensed health
    GET  /agent/<name>       Detailed single-agent view
    GET  /graph              Dependency graph JSON
    GET  /logs/<name>        Last N lines of agent log
    GET  /env                Env-var map (values masked)
    GET  /heartbeat          Orchestrator liveness probe
    POST /restart/<name>     Trigger manual restart
    POST /stop/<name>        Stop agent
    POST /start/<name>       Start agent
    """

    def log_message(self, fmt: str, *args) -> None:  # suppress default access log
        pass

    # ── Routing ───────────────────────────────────────────────────────────────

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path == "/status":
            self._send_json(_get_status())
        elif path == "/agents":
            self._send_json(_get_agents())
        elif path.startswith("/agent/"):
            name = path[len("/agent/"):]
            detail = _supervisor.agent_detail(name) if _supervisor else None
            if detail:
                self._send_json(detail)
            else:
                self._send_json({"error": f"agent '{name}' not found"}, 404)
        elif path == "/graph":
            self._send_json(_supervisor._graph.as_dict() if _supervisor else {})
        elif path.startswith("/logs/"):
            name = path[len("/logs/"):]
            lines = _supervisor.log_tail(name) if _supervisor else []
            self._send_json({"agent": name, "lines": lines, "count": len(lines)})
        elif path == "/env":
            self._send_json(_get_env_map())
        elif path == "/heartbeat":
            self._send_json({
                "status": "ok",
                "ts": datetime.now(timezone.utc).isoformat(),
                "uptime_s": _uptime_s(),
            })
        else:
            self._send_json({"error": "endpoint not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path.startswith("/restart/"):
            name = path[len("/restart/"):]
            ok = _supervisor.restart_agent(name) if _supervisor else False
            self._send_json({"agent": name, "action": "restart", "ok": ok})
        elif path.startswith("/stop/"):
            name = path[len("/stop/"):]
            ok = _supervisor.stop_agent(name) if _supervisor else False
            self._send_json({"agent": name, "action": "stop", "ok": ok})
        elif path.startswith("/start/"):
            name = path[len("/start/"):]
            ok = _supervisor.start_agent(name) if _supervisor else False
            self._send_json({"agent": name, "action": "start", "ok": ok})
        else:
            self._send_json({"error": "endpoint not found"}, 404)

    # ── Response helper ───────────────────────────────────────────────────────

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Data helpers for API ───────────────────────────────────────────────────────

_start_time = time.monotonic()


def _uptime_s() -> float:
    return round(time.monotonic() - _start_time, 1)


def _get_status() -> Dict:
    if not _supervisor:
        return {"status": "initialising"}
    snap = _supervisor.health_snapshot()
    healthy = sum(1 for s in snap.values() if s["healthy"])
    total = len(snap)
    return {
        "status": "ok",
        "ts": datetime.now(timezone.utc).isoformat(),
        "uptime_s": _uptime_s(),
        "agents": {
            "total": total,
            "healthy": healthy,
            "degraded": total - healthy,
        },
        "recent_events": _supervisor.recent_events(10),
    }


def _get_agents() -> List[Dict]:
    if not _supervisor:
        return []
    snap = _supervisor.health_snapshot()
    result = []
    for name, health in snap.items():
        detail = _supervisor.agent_detail(name) or {}
        result.append({
            "name": name,
            "port": detail.get("port"),
            "pid": detail.get("pid"),
            "uptime_s": detail.get("uptime_s"),
            "running": _supervisor._pm.is_running(name),
            "healthy": health["healthy"],
            "cpu_pct": health.get("cpu_pct", 0),
            "mem_pct": health.get("mem_pct", 0),
            "restart_count": detail.get("restart_count", 0),
            "last_restart": detail.get("last_restart"),
            "failure_reason": health.get("failure_reason", ""),
        })
    return result


def _get_env_map() -> Dict:
    """Return env-var names per agent with values masked (security boundary)."""
    if not _supervisor:
        return {}
    result = {}
    for name, agent in _supervisor._agents.items():
        result[name] = {
            key: ("***set***" if os.environ.get(key) else "not_set")
            for key in agent.get("env", [])
        }
    return result


def _run_api(host: str, port: int) -> None:
    server = HTTPServer((host, port), _APIHandler)
    orch_log.info("Control-plane API listening on http://%s:%d/", host, port)
    orch_log.info("Endpoints: /status /agents /agent/<n> /graph /logs/<n> /env /heartbeat")
    orch_log.info("Actions:   POST /restart/<n>  /stop/<n>  /start/<n>")
    server.serve_forever()


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    global _supervisor

    parser = argparse.ArgumentParser(
        description="FractalMesh Sovereign Orchestrator — Mode B"
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help=f"Path to registry.yaml (default: {DEFAULT_REGISTRY})",
    )
    parser.add_argument(
        "--no-start",
        action="store_true",
        help="Load registry and start API without launching agents (dry-run)",
    )
    args = parser.parse_args()

    orch_log.info("=" * 70)
    orch_log.info("FractalMesh Sovereign Orchestrator — Mode B")
    orch_log.info("Base directory : %s", BASE_DIR)
    orch_log.info("Registry       : %s", args.registry)
    orch_log.info(
        "Optional deps  : pyyaml=%s  psutil=%s  requests=%s",
        HAS_YAML, HAS_PSUTIL, HAS_REQUESTS,
    )
    orch_log.info("=" * 70)

    # ── Load agents ───────────────────────────────────────────────────────────
    agents = load_registry(args.registry)
    if not agents:
        orch_log.critical("No agents found. Aborting.")
        sys.exit(1)

    # ── Wire components ───────────────────────────────────────────────────────
    graph = DependencyGraph(agents)
    proc_mgr = ProcessManager()
    health_chkr = HealthChecker(proc_mgr)
    supervisor = Supervisor(agents, graph, proc_mgr, health_chkr)
    _supervisor = supervisor

    orch_log.info(
        "Dependency start order: %s", " → ".join(graph.topological_start_order())
    )

    # ── Start agents ──────────────────────────────────────────────────────────
    if not args.no_start:
        orch_log.info("Starting agents in dependency order …")
        supervisor.start_all()
    else:
        orch_log.info("--no-start flag set; agents not launched.")

    # ── Supervisor thread ─────────────────────────────────────────────────────
    sup_thread = threading.Thread(
        target=supervisor.run, daemon=True, name="supervisor-loop"
    )
    sup_thread.start()

    # ── API thread ────────────────────────────────────────────────────────────
    api_thread = threading.Thread(
        target=_run_api, args=(API_HOST, API_PORT), daemon=True, name="api"
    )
    api_thread.start()

    # ── Shutdown handlers ─────────────────────────────────────────────────────
    def _shutdown(sig, _frame):
        orch_log.info("Signal %d received — stopping all agents …", sig)
        supervisor.stop()
        supervisor.stop_all()
        orch_log.info("Orchestrator shutdown complete.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    orch_log.info(
        "Orchestrator operational.  Control plane: http://%s:%d/",
        API_HOST, API_PORT,
    )

    # Keep the main thread alive; let daemon threads do the work
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
