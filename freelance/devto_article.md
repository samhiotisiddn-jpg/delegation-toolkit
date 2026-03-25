# Dev.to Article Draft

## Title
I Run 13 Autonomous Python Agents on My Android Phone (Here's How)

## Tags
python, android, automation, termux

## Cover Image
Screenshot of your PM2 status table showing all 13 agents running
(the one you already have on your phone)

---

## Article Body

Most tutorials assume you have a server.

I don't. I have an Android phone, Termux, and a 250MB memory limit.
This is what running 13 autonomous Python agents looks like inside that constraint.

### What I built

A multi-agent orchestration system that runs permanently in the background on Android.
Each agent is an independent Python process with a specific job:

| Agent | Memory | Function |
|-------|--------|----------|
| geosignal | 28.4mb | ISS position + solar Kp index |
| fm-dashboard | 30.2mb | Web monitoring interface |
| fm-signals | 11.3mb | Crypto price tracking |
| fm-pod | 30.2mb | Product/billing bridge |
| fm-dorking | 25.6mb | Lead discovery |
| (+ 8 more) | | |

Total: 211.6mb. Buffer: 38.4mb. Fits on a $200 phone.

### The stack

- **Termux** on Android (F-Droid version)
- **proot-debian** for a full Linux environment
- **Python 3** with Flask, requests, sqlite3
- **PM2** (yes, the Node.js process manager — works perfectly for Python)
- **SQLite** for inter-agent state sharing

### The key insight: memory discipline

Most Python processes bloat because of imports. The trick is lazy loading —
only import what you need, when you need it.

```python
# BAD — loads everything at startup
import pandas as pd
import numpy as np
import requests
import sqlite3

# GOOD — load at point of use
def fetch_price():
    import requests  # Only loaded when this function runs
    return requests.get(...).json()
```

Each agent follows the same 20-line template:

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
    # Your agent logic here
    pass

def main():
    log.info("Agent starting")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Cycle error: {e}")
        time.sleep(60)  # Adjust per agent

if __name__ == '__main__':
    main()
```

### PM2 on Android

PM2 manages all 13 agents with auto-restart, log rotation, and cron scheduling.
Install it once:

```bash
pkg install nodejs-lts
npm install -g pm2
```

Ecosystem config (excerpt):

```javascript
module.exports = {
  apps: [
    {
      name: "geosignal",
      script: "/root/geosignal/geosignal.py",
      interpreter: "python3",
      autorestart: true,
      max_restarts: 50,
      cron_restart: "*/15 * * * *",
      env: { PYTHONUNBUFFERED: "1" }
    },
    // ... 12 more
  ]
};
```

`pm2 start ecosystem.config.js` launches everything. `pm2 status` shows the table.

### The GeoSignal agent

The most interesting one polls three free APIs every 60 seconds:

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
    return float(r.json()[-1][1])  # Latest Kp value
```

Both APIs are free, no key required. The agent logs ISS position and solar
activity to SQLite, which the dashboard reads.

### What I learned

1. **Constrained environments force good habits.** Every import costs memory.
   Every sleep interval costs battery. You write leaner code.

2. **PM2 is underrated for Python.** It handles crash recovery, log rotation,
   and scheduled restarts better than most Python-native solutions.

3. **SQLite is enough.** For coordination between 13 agents on one device,
   you don't need Redis or a proper database server.

4. **Android is a real Linux machine.** With proot-debian, you have apt,
   pip, npm, sqlite3, curl — the full toolchain.

### Want the full setup guide?

I wrote a complete step-by-step guide including the deploy/repair scripts,
the full ecosystem config, and the SQLite schema:

[13 Agents on a Phone — Full Guide on Gumroad]($29 AUD)

Or if you want me to build a custom agent system for your project:
[Find me on Upwork](https://www.upwork.com/freelancers/samhiotis)

---

*Samuel Hiotis | Python Automation Engineer | Albury NSW*
*ABN 56 628 117 363*
