#!/usr/bin/env bash
# 🧠 Codex-Thinker: AI Decision Engine with Provider Cascade
# All credentials injected via GitHub Secrets (never hardcoded)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/../logs"
OUTPUT_DIR="${SCRIPT_DIR}/../output"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

LOG_FILE="$LOG_DIR/codex-thinker.log"
DECISION_FILE="$OUTPUT_DIR/approved_action_$(date +%s).txt"

# Colors for output
C='\033[0;36m'
G='\033[0;32m'
Y='\033[1;33m'
R='\033[0;31m'
NC='\033[0m'

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ─────────────────────────────────────────────────────────────────────
# PROVIDER CASCADE: Try AI providers in order until one works
# ────────────────���────────────────────────────────────────────────────

call_anthropic() {
    local prompt="$1"
    
    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        return 1
    fi
    
    log "🤖 Trying Anthropic Claude..."
    
    response=$(curl -s -X POST https://api.anthropic.com/v1/messages \
        -H "x-api-key: $ANTHROPIC_API_KEY" \
        -H "anthropic-version: 2023-06-01" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"claude-3-5-sonnet-20241022\",
            \"max_tokens\": 500,
            \"messages\": [{
                \"role\": \"user\",
                \"content\": \"$prompt\"
            }]
        }" 2>&1)
    
    # Check for errors
    if echo "$response" | grep -q "error"; then
        log "❌ Anthropic failed: $(echo "$response" | grep -o '"message":"[^"]*' | head -1)"
        return 1
    fi
    
    # Extract response
    echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['content'][0]['text'])" 2>/dev/null || return 1
}

call_openrouter() {
    local prompt="$1"
    
    if [ -z "${OPENROUTER_API_KEY:-}" ]; then
        return 1
    fi
    
    log "🤖 Trying OpenRouter (free models)..."
    
    response=$(curl -s -X POST https://openrouter.ai/api/v1/chat/completions \
        -H "Authorization: Bearer $OPENROUTER_API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"meta-llama/llama-3.2-3b-instruct:free\",
            \"messages\": [{
                \"role\": \"user\",
                \"content\": \"$prompt\"
            }],
            \"max_tokens\": 500
        }" 2>&1)
    
    if echo "$response" | grep -q "error"; then
        log "❌ OpenRouter failed"
        return 1
    fi
    
    echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['choices'][0]['message']['content'])" 2>/dev/null || return 1
}

call_openai() {
    local prompt="$1"
    
    if [ -z "${OPENAI_API_KEY:-}" ]; then
        return 1
    fi
    
    log "🤖 Trying OpenAI GPT (fallback)..."
    
    response=$(curl -s -X POST https://api.openai.com/v1/chat/completions \
        -H "Authorization: Bearer $OPENAI_API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"gpt-4o-mini\",
            \"messages\": [{
                \"role\": \"user\",
                \"content\": \"$prompt\"
            }],
            \"max_tokens\": 500
        }" 2>&1)
    
    if echo "$response" | grep -q "error"; then
        log "❌ OpenAI failed"
        return 1
    fi
    
    echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['choices'][0]['message']['content'])" 2>/dev/null || return 1
}

get_ai_response() {
    local prompt="$1"
    
    # Try providers in cascade order
    call_anthropic "$prompt" && return 0
    call_openrouter "$prompt" && return 0
    call_openai "$prompt" && return 0
    
    log "❌ All AI providers failed"
    return 1
}

# ─────────────────────────────────────────────────────────────────────
# CONFIDENCE SCORING
# ─────────────────────────────────────────────────────────────────────

calculate_confidence() {
    local text="$1"
    
    # Count bullish/bearish keywords
    local bullish_count=0
    local bearish_count=0
    
    bullish_keywords=("bullish" "strong" "support" "momentum" "opportunity" "buying" "uptick" "growth")
    bearish_keywords=("bearish" "weak" "resistance" "decline" "caution" "selling" "downturn" "risk")
    
    for keyword in "${bullish_keywords[@]}"; do
        bullish_count=$((bullish_count + $(echo "$text" | grep -io "$keyword" | wc -l)))
    done
    
    for keyword in "${bearish_keywords[@]}"; do
        bearish_count=$((bearish_count + $(echo "$text" | grep -io "$keyword" | wc -l)))
    done
    
    # Calculate confidence (0.0 to 1.0)
    local total=$((bullish_count + bearish_count))
    
    if [ $total -eq 0 ]; then
        echo "0.50"  # Neutral
        return 0
    fi
    
    local confidence=$(echo "scale=2; $bullish_count / ($bullish_count + $bearish_count)" | bc)
    echo "$confidence"
}

# ─────────────────────────────────────────────────────────────────────
# MAIN EXECUTION
# ─────────────────────────────────────────────────────────────────────

log ""
log "═══════════════════════════════════════════════════════════════════"
log "🧠 CODEX-THINKER CYCLE INITIATED"
log "═══════════════════════════════════════════════════════════════════"

TIMESTAMP=$(date +%s)

# Build market analysis prompt
MARKET_PROMPT="You are a professional crypto trading signal generator. Analyze the following and provide a concise trading signal (BULLISH/BEARISH) with confidence:

Current Market Context:
- BTC-USDT: ~$95,000 USD
- ETH-USDT: ~$3,500 USD
- Market Cap: ~$3.5T
- Dominance: BTC 52%, ETH 18%

Provide:
1. Analysis (2-3 sentences)
2. Signal: BULLISH / BEARISH / NEUTRAL
3. Confidence: 0.0-1.0

Be concise and quantitative."

log "📊 Generating market analysis..."

# Call AI with cascade fallback
ANALYSIS=$(get_ai_response "$MARKET_PROMPT") || {
    log "❌ Failed to get AI analysis"
    exit 1
}

log "✅ Analysis received:"
log "$ANALYSIS"

# Calculate confidence from response
CONFIDENCE=$(calculate_confidence "$ANALYSIS")

log "📊 Confidence Score: $CONFIDENCE"

# Consensus threshold from GitHub Secrets (default 0.60)
THRESHOLD=${CONSENSUS_THRESHOLD:-0.60}

if (( $(echo "$CONFIDENCE >= $THRESHOLD" | bc -l) )); then
    log "✅ CONSENSUS REACHED ($CONFIDENCE >= $THRESHOLD)"
    
    # Create execution flag for Grid-Sync
    EXECUTION_FLAG="${SCRIPT_DIR}/../recon/trigger_execution.flag"
    mkdir -p "$(dirname "$EXECUTION_FLAG")"
    
    cat > "$EXECUTION_FLAG" << EOF
TIMESTAMP=$TIMESTAMP
CONFIDENCE=$CONFIDENCE
ANALYSIS=$ANALYSIS
ACTION=BUY
PAIR=BTC-USDT
SIZE=$(echo "$MAX_TRADE_SIZE_BTC" | bc || echo "0.001")
DRY_RUN=${DRY_RUN:-false}
EOF
    
    log "🎯 EXECUTION FLAG CREATED: $EXECUTION_FLAG"
    
    # Save decision to output
    cat > "$DECISION_FILE" << EOF
═══════════════════════════════════════════════════════════════════
APPROVED ACTION - $(date)
═══════════════════════════════════════════════════════════════════
Confidence: $CONFIDENCE
Threshold: $THRESHOLD
Analysis: $ANALYSIS

Execution Flag: $EXECUTION_FLAG
Status: PENDING GRID-SYNC EXECUTION
═══════════════════════════════════════════════════════════════════
EOF
    
    log "📋 Decision saved to: $DECISION_FILE"
    
else
    log "⏸️  Consensus not reached ($CONFIDENCE < $THRESHOLD)"
    log "Waiting for next cycle..."
fi

log "═══════════════════════════════════════════════════════════════════"
log "✅ Codex-Thinker cycle complete"
log "═══════════════════════════════════════════════════════════════════"
log ""

# Cool down before next execution
COOLDOWN=${CODEX_COOLDOWN:-30}
log "⏸️  Cooling down for ${COOLDOWN}s..."
sleep "$COOLDOWN"
