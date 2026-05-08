"""Firebase REST API integration — Firestore, Auth, Realtime DB."""
import os
import json
import logging
import urllib.request
import urllib.parse

log = logging.getLogger("firebase_client")

_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "iddn-portal")
_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "")
_FIRESTORE_BASE = f"https://firestore.googleapis.com/v1/projects/{_PROJECT_ID}/databases/(default)/documents"
_RTDB_URL = os.getenv("FIREBASE_RTDB_URL", f"https://{_PROJECT_ID}-default-rtdb.firebaseio.com")


def _get(url: str, token: str | None = None) -> dict:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _post(url: str, body: dict, token: str | None = None) -> dict:
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def sign_in_anonymous() -> dict:
    """Sign in anonymously to get an ID token."""
    if not _WEB_API_KEY:
        return {"error": "FIREBASE_WEB_API_KEY not set"}
    try:
        return _post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={_WEB_API_KEY}",
            {"returnSecureToken": True},
        )
    except Exception as exc:
        log.warning("firebase sign_in_anonymous: %s", exc)
        return {"error": str(exc)}


def rtdb_set(path: str, data: dict, token: str | None = None) -> dict:
    """Write to Firebase Realtime Database at path."""
    url = f"{_RTDB_URL}/{path.lstrip('/')}.json"
    if token:
        url += f"?auth={token}"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as exc:
        log.warning("rtdb_set %s: %s", path, exc)
        return {"error": str(exc)}


def rtdb_get(path: str, token: str | None = None) -> dict:
    """Read from Firebase Realtime Database."""
    url = f"{_RTDB_URL}/{path.lstrip('/')}.json"
    if token:
        url += f"?auth={token}"
    try:
        return _get(url)
    except Exception as exc:
        log.warning("rtdb_get %s: %s", path, exc)
        return {"error": str(exc)}


def push_metrics(metrics: dict) -> dict:
    """Push a metrics snapshot to RTDB /fractalmesh/metrics."""
    import time
    metrics["server_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return rtdb_set("fractalmesh/metrics", metrics)


def push_alert(title: str, body: str, level: str = "info") -> dict:
    import time
    return rtdb_set(f"fractalmesh/alerts/{int(time.time())}", {
        "title": title, "body": body, "level": level,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
