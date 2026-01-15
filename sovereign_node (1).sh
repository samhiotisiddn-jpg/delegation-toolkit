#!/bin/bash
# =================================================================
# FRACTALMESH SOVEREIGN NODE - FULLY AUTONOMOUS MASTER
# =================================================================

PROJECT_DIR="$HOME/fractalmesh"
LOG_DIR="$PROJECT_DIR/logs"
ENV_FILE="$PROJECT_DIR/.env"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

echo "💎 Initializing Sovereign Trading Node..."

# 1. DISK AUDIT & LOG ROTATION (Prevents Errno 28)
AVAILABLE_MB=$(df -m /data | awk 'NR==2 {print $4}')
if [ "$AVAILABLE_MB" -lt 50 ]; then
    echo "⚠️ Space low (${AVAILABLE_MB}MB). Purging old logs to stay alive..."
    rm -rf "$LOG_DIR"/*.jsonl "$LOG_DIR"/*.log
fi

# 2. AUTONOMOUS FILE WRITING (Writing the Trading Logic)
cat << 'PY_EOF' > "$PROJECT_DIR/trading_empire.py"
import os, requests, hmac, hashlib, base64, time, json
from datetime import datetime

# MANUAL ENV LOADER (Bypasses missing 'dotenv' module)
def load_secrets():
    secrets = {}
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    secrets[k.strip()] = v.strip()
    return secrets

SECRETS = load_secrets()

class TradingNode:
    def __init__(self):
        self.kucoin_key = SECRETS.get('KUCOIN_KEY')
        self.cdc_key = SECRETS.get('CDC_KEY')
        print(f"✅ Credentials Loaded: {'LIVE' if self.kucoin_key else 'MOCK'}")

    def run(self):
        while True:
            # Main revenue loop logic here
            time.sleep(15)

if __name__ == "__main__":
    node = TradingNode()
    node.run()
PY_EOF

# 3. LAUNCH IN BACKGROUND
echo "🚀 Launching Trading Empire (PID recording to logs)..."
nohup python3 trading_empire.py >> "$LOG_DIR/trading.log" 2>&1 &
PID=$!

echo "------------------------------------------------------------"
echo "✅ SYSTEM LIVE | PID: $PID"
echo "📊 AUDIT LOG: tail -f $LOG_DIR/trading.log"
echo "------------------------------------------------------------"

# 4. PERSISTENCE CHECK
while ps -p $PID > /dev/null; do
    echo -ne "Status: 🟢 RUNNING | Free Space: ${AVAILABLE_MB}MB\r"
    sleep 30
done
echo -e "\n🔴 ENGINE HALTED. Check logs."
