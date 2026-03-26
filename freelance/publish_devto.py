#!/usr/bin/env python3
"""
Publish the Dev.to article using your Dev.to API key.
Run: python3 publish_devto.py
Set DEVTO_API_KEY in your environment first.
"""
import os
import requests
import json

DEVTO_API_KEY = os.getenv("DEVTO_API_KEY")
if not DEVTO_API_KEY:
    print("ERROR: Set DEVTO_API_KEY environment variable first.")
    print("  export DEVTO_API_KEY=your_key_here")
    print("  Get it from: https://dev.to/settings/extensions")
    exit(1)

ARTICLE_BODY = """
I Run 13 Autonomous Python Agents on My Android Phone (Here's How)

Most tutorials assume you have a server.

I don't. I have an Android phone, Termux, and a 250MB memory limit.
This is what running 13 autonomous Python agents looks like inside that constraint.

## What I built

A multi-agent orchestration system that runs permanently in the background on Android.
Each agent is an independent Python process with a specific job:

| Agent | Memory | Function |
|-------|--------|----------|
| geosignal | 28.4mb | ISS position + solar Kp index |
| fm-dashboard | 30.2mb | Web monitoring interface |
| fm-signals | 11.3mb | Crypto price tracking |
| fm-pod | 30.2mb | Product/billing bridge |
| fm-dorking | 25.6mb | Lead discovery |

Total: 211.6mb. Buffer: 38.4mb. Fits on a $200 phone.

## The stack

- **Termux** on Android (F-Droid version)
- **proot-debian** for a full Linux environment
- **Python 3** with Flask, requests, sqlite3
- **PM2** (yes, the Node.js process manager — works perfectly for Python)
- **SQLite** for inter-agent state sharing

## The key insight: memory discipline

Most Python processes bloat because of imports. The trick is lazy loading —
only import what you need, when you need it.

```python
# BAD — loads everything at startup
import pandas as pd
import numpy as np

# GOOD — load at point of use
def fetch_price():
    import requests
    return requests.get(...).json()
```

Each agent follows the same base template:

```python
#!/usr/bin/env python3
import os, time, sqlite3, logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [AgentName] %(message)s',
    handlers=[
        logging.FileHandler('/root/fmsaas/logs/agent.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('agent')

DB = '/root/fmsaas/database/sovereign.db'

def run_cycle():
    pass  # Your agent logic here

def main():
    log.info("Agent starting")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Cycle error: {e}")
        time.sleep(60)

if __name__ == '__main__':
    main()
```

## PM2 on Android

```bash
pkg install nodejs-lts
npm install -g pm2
```

```javascript
module.exports = {
  apps: [{
    name: "geosignal",
    script: "/root/geosignal/geosignal.py",
    interpreter: "python3",
    autorestart: true,
    max_restarts: 50,
    cron_restart: "*/15 * * * *",
    env: { PYTHONUNBUFFERED: "1" }
  }]
};
```

## The GeoSignal agent (live satellite data, free)

```python
def iss():
    r = requests.get('http://api.open-notify.org/iss-now.json', timeout=5)
    pos = r.json()['iss_position']
    return float(pos['latitude']), float(pos['longitude'])

def solar_kp():
    r = requests.get(
        'https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json',
        timeout=6
    )
    return float(r.json()[-1][1])
```

Both APIs are free, no key required.

## What I learned

1. Constrained environments force good habits. Every import costs memory.
2. PM2 is underrated for Python — handles crash recovery and log rotation well.
3. SQLite is enough for 13 agents on one device.
4. Android is a real Linux machine with proot-debian.

## Want the full setup guide?

I wrote a complete step-by-step guide — deploy scripts, ecosystem config, SQLite schema, memory optimisation tricks:

**[Get the full guide — $29 AUD on Gumroad](https://gumroad.com/samhiotis)**

Or if you want me to build a custom agent system:
**[Upwork profile](https://www.upwork.com/freelancers/samhiotis)**

---
*Samuel Hiotis | Python Automation Engineer | Albury NSW | ABN 56 628 117 363*
"""

payload = {
    "article": {
        "title": "I Run 13 Autonomous Python Agents on My Android Phone (Here's How)",
        "published": True,
        "body_markdown": ARTICLE_BODY,
        "tags": ["python", "android", "automation", "termux"],
        "description": "Running 13 autonomous Python agents on Android with Termux and PM2 — under a 250MB memory budget."
    }
}

headers = {
    "api-key": DEVTO_API_KEY,
    "Content-Type": "application/json"
}

print("Publishing to Dev.to...")
r = requests.post("https://dev.to/api/articles", json=payload, headers=headers)

if r.status_code == 201:
    data = r.json()
    print(f"\nSUCCESS!")
    print(f"  Title: {data['title']}")
    print(f"  URL:   {data['url']}")
    print(f"  ID:    {data['id']}")
    print(f"\nArticle is LIVE. Share this link everywhere.")
else:
    print(f"\nFAILED: HTTP {r.status_code}")
    print(r.text)
    print("\nCheck your DEVTO_API_KEY at https://dev.to/settings/extensions")
