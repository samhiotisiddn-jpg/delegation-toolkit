#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# PLUG EVERYTHING IN — Run this on your Termux/Debian device
# Sets up Dev.to + Gumroad in one go
# Usage: bash plug_in.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -e

G='\033[0;32m'; Y='\033[1;33m'; C='\033[0;36m'; R='\033[0;31m'; W='\033[0m'

ok()  { echo -e "${G}[✓]${W} $*"; }
inf() { echo -e "${C}[→]${W} $*"; }
err() { echo -e "${R}[✗]${W} $*"; }

echo ""
echo -e "${Y}╔══════════════════════════════════════════════════════════╗${W}"
echo -e "${Y}║  FRACTALMESH — PLUG EVERYTHING IN                       ║${W}"
echo -e "${Y}║  Samuel James Hiotis | ABN 56 628 117 363               ║${W}"
echo -e "${Y}╚══════════════════════════════════════════════════════════╝${W}"
echo ""

# ── STEP 1: Load keys from vault ─────────────────────────────────────────────

VAULT="${VAULT:-$HOME/fmsaas/vault/.env}"

if [ -f "$VAULT" ]; then
    inf "Loading credentials from vault: $VAULT"
    set -a
    # shellcheck disable=SC1090
    source "$VAULT"
    set +a
    ok "Vault loaded"
else
    err "Vault not found at $VAULT"
    echo "  Set VAULT=/path/to/.env or ensure $HOME/fmsaas/vault/.env exists"
fi

# Keys may also come from environment directly
DEVTO_KEY="${DEVTO_API_KEY:-}"
GUMROAD_KEY="${GUMROAD_ACCESS_TOKEN:-}"

# Report what was found
[ -n "$DEVTO_KEY" ]   && ok "Dev.to API key found"   || echo -e "${Y}[!]${W} DEVTO_API_KEY not in vault"
[ -n "$GUMROAD_KEY" ] && ok "Gumroad token found"    || echo -e "${Y}[!]${W} GUMROAD_ACCESS_TOKEN not in vault"

echo ""

# ── STEP 2: Install dependencies ─────────────────────────────────────────────
inf "Installing Python requests..."
pip3 install --quiet requests 2>/dev/null || pip install --quiet requests 2>/dev/null || true
ok "Dependencies ready"

# ── STEP 3: Publish Dev.to article ───────────────────────────────────────────
if [ -n "$DEVTO_KEY" ]; then
    inf "Publishing Dev.to article..."
    export DEVTO_API_KEY="$DEVTO_KEY"
    python3 "$(dirname "$0")/publish_devto.py"
else
    echo -e "${Y}[skip]${W} Dev.to — no key provided"
    echo "       Run later: export DEVTO_API_KEY=your_key && python3 publish_devto.py"
fi

echo ""

# ── STEP 4: Create Gumroad product ───────────────────────────────────────────
if [ -n "$GUMROAD_KEY" ]; then
    inf "Creating Gumroad product..."
    export GUMROAD_ACCESS_TOKEN="$GUMROAD_KEY"
    python3 "$(dirname "$0")/create_gumroad_product.py"
else
    echo -e "${Y}[skip]${W} Gumroad — no token provided"
    echo "       Run later: export GUMROAD_ACCESS_TOKEN=your_token && python3 create_gumroad_product.py"
fi

echo ""

# ── STEP 5: Upwork instructions ───────────────────────────────────────────────
inf "Upwork (manual — 5 minutes):"
echo "  1. Go to https://www.upwork.com/freelancer/signup"
echo "  2. Copy your profile from: freelance/upwork_profile.md"
echo "  3. Set hourly rate: \$65 AUD"
echo "  4. Search 'Python automation' and bid on 5 jobs today"

echo ""
echo -e "${G}╔══════════════════════════════════════════════════════════╗${W}"
echo -e "${G}║  DONE — Income streams plugged in                        ║${W}"
echo -e "${G}║                                                          ║${W}"
echo -e "${G}║  Dev.to article → drives traffic to Gumroad + Upwork     ║${W}"
echo -e "${G}║  Gumroad product → \$29 AUD per sale, instant delivery   ║${W}"
echo -e "${G}║  Upwork profile → \$65/hr freelance work                  ║${W}"
echo -e "${G}╚══════════════════════════════════════════════════════════╝${W}"
echo ""
