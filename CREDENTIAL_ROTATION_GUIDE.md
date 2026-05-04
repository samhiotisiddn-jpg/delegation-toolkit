# Credential Rotation Guide

## URGENT: Exposed Credentials Requiring Immediate Rotation

This repository contained hardcoded API keys in tracked files. Those values have been
replaced with `<REDACTED_ROTATE_IMMEDIATELY>` placeholders. You must rotate every
credential listed below as soon as possible — treat them all as compromised.

---

## Critical Priority (Rotate First)

### 1. Ethereum / Crypto Private Keys & Seed Phrases

**Risk: Total and permanent loss of funds if exploited.**

| Credential | Action Required |
|---|---|
| Ethereum private key (wallet `0x50c494d57577d6d1da7c29ac331916e2f9c3bb85`) | Transfer ALL funds to a new wallet immediately. Generate a new wallet with a fresh seed phrase in a hardware wallet or air-gapped device. |
| Crypto.com wallet seed phrase | Create a new wallet, transfer funds, discard the old seed phrase. |
| Secondary wallet seed phrase | Create a new wallet, transfer funds, discard the old seed phrase. |
| XYO network seed phrase | Create a new XYO wallet, transfer stake/funds. |
| Aleo private key | Generate new key pair via `aleo account new`. Transfer any balance. |
| EOS private key | Use `cleos wallet` or a trusted EOS wallet to generate a new key. Update account permissions. |
| HBAR (Hedera) private key | Generate new key in Hedera portal. Rotate account keys. |

**How to generate a new Ethereum wallet:**
```bash
# Using ethers.js (Node.js)
node -e "const {ethers} = require('ethers'); const w = ethers.Wallet.createRandom(); console.log('Address:', w.address); console.log('Key:', w.privateKey); console.log('Mnemonic:', w.mnemonic.phrase);"
```

---

## High Priority (Exchange API Keys)

Revoke and regenerate these immediately. Exchange API keys with withdrawal permissions
can drain accounts.

### 2. KuCoin
- **Console:** https://www.kucoin.com/account/api
- **Action:** Delete existing API keys → Create new key → Update `.env`
- **Note:** Ensure new key has minimal permissions (read + trade only, no withdrawal)

### 3. Pionex
- **Console:** https://www.pionex.com/en/account/api
- **Action:** Revoke existing key → Generate new key → Update `.env`

### 4. Crypto.com (CDC)
- **Console:** https://crypto.com/exchange/personal/api-management
- **Action:** Delete existing API keys → Create new ones

### 5. Stripe (Live Secret Key)
- **Console:** https://dashboard.stripe.com/apikeys
- **Action:** Roll the secret key immediately (Stripe provides a "Roll key" button)
- **Risk:** Live payment processing credentials — extremely sensitive

---

## High Priority (AI / Cloud API Keys)

### 6. Anthropic API Key
- **Console:** https://console.anthropic.com/settings/keys
- **Action:** Delete compromised key → Create new key

### 7. OpenAI API Key
- **Console:** https://platform.openai.com/api-keys
- **Action:** Delete key → Create new key

### 8. xAI (Grok) API Key
- **Console:** https://console.x.ai/
- **Action:** Revoke key → Generate new one

### 9. HuggingFace Token
- **Console:** https://huggingface.co/settings/tokens
- **Action:** Delete token → Create new token with minimal required permissions

### 10. OpenRouter API Key
- **Console:** https://openrouter.ai/keys
- **Action:** Delete key → Create new key

### 11. ElevenLabs API Key
- **Console:** https://elevenlabs.io/app/profile-settings
- **Action:** Regenerate API key

### 12. LangSmith API Key
- **Console:** https://smith.langchain.com/settings
- **Action:** Delete key → Create new key

---

## High Priority (Infrastructure / DevOps)

### 13. GitHub Personal Access Tokens (PATs)
- **Console:** https://github.com/settings/tokens
- **Action:** Delete all exposed PATs → Generate new tokens with minimum required scopes

### 14. Docker Hub PAT
- **Console:** https://hub.docker.com/settings/security
- **Action:** Delete token → Create new token

### 15. Alchemy API Key
- **Console:** https://dashboard.alchemy.com/
- **Action:** Regenerate API key for affected apps

### 16. Pinecone API Key
- **Console:** https://app.pinecone.io/
- **Action:** Regenerate API key

### 17. Firebase Web API Key
- **Console:** https://console.firebase.google.com/ → Project Settings → General
- **Action:** Delete browser key → Create new restricted key

### 18. Google GenLang / AI API Key
- **Console:** https://console.cloud.google.com/apis/credentials
- **Action:** Delete key → Create new key with appropriate restrictions

---

## Medium Priority (Communication & Social)

### 19. Telegram Bot Token
- **Action:** Message `@BotFather` on Telegram → `/revoke` → select your bot → get new token

### 20. Gmail App Password
- **Console:** https://myaccount.google.com/apppasswords
- **Action:** Delete exposed app password → Create a new one

### 21. Twitter / X Access Token
- **Console:** https://developer.twitter.com/en/portal/dashboard
- **Action:** Regenerate access token and secret

### 22. SendGrid API Key
- **Console:** https://app.sendgrid.com/settings/api_keys
- **Action:** Delete key → Create new key

### 23. ProductHunt API Key
- **Console:** https://www.producthunt.com/v2/oauth/applications
- **Action:** Regenerate API key

### 24. WiGLE API Token
- **Console:** https://wigle.net/account
- **Action:** Revoke token → Generate new token

---

## Medium Priority (Other Services)

### 25. BugCrowd API Token
- **Console:** https://tracker.bugcrowd.com/settings/api
- **Action:** Revoke token → Create new token

### 26. Latitude API Key
- **Console:** https://app.latitude.so/settings
- **Action:** Revoke key → Generate new one

### 27. Tipbot Auth Key
- **Action:** Contact the tipbot service to revoke and reissue

---

## Banking & Personal Information

### 28. Bankwest Account Credentials
- **Action:** **Change your internet banking password immediately.**
  - Log in at https://ibs.bankwest.com.au/
  - Go to Security Settings → Change Password
  - Enable two-factor authentication if not already enabled
  - Contact Bankwest fraud team if any unauthorized transactions are observed: **1300 19 1000**

### 29. Tax File Number (TFN)
- A TFN cannot be "rotated" but its exposure should be reported.
- **Action:** Contact the Australian Tax Office (ATO) on **13 28 61** to report potential TFN compromise.

---

## Files Modified in This Commit

The following repository files had credentials replaced with `<REDACTED_ROTATE_IMMEDIATELY>`:

| File | Credentials Removed |
|---|---|
| `DEPLOYMENT_SUCCESS.txt` | HuggingFace token, Pinecone API key, DEV.to API key, KuCoin API key, Pionex API key |
| `PROVIDER_GUIDE.txt` | KuCoin API key (inline example) |

---

## Preventing Future Exposure

### 1. Never commit credentials directly

Always store secrets in environment variables and load them at runtime:

```bash
# .env (never commit this file)
KUCOIN_API_KEY=your_real_key_here

# In your script
source .env
```

### 2. Add `.env` and secret files to `.gitignore`

The `.gitignore` in this repository has been updated to exclude common secret files.

### 3. Use a secrets manager

Consider using:
- **AWS Secrets Manager** / **Azure Key Vault** / **GCP Secret Manager**
- **HashiCorp Vault** (self-hosted)
- **Doppler** (developer-friendly SaaS)

### 4. Scan before every commit

Install `gitleaks` or `truffleHog` to catch secrets before they reach git history:

```bash
# Install gitleaks
brew install gitleaks  # macOS
# or
go install github.com/gitleaks/gitleaks/v8@latest

# Run scan
gitleaks detect --source .
```

### 5. GitHub secret scanning

Enable GitHub's built-in secret scanning in your repository:
- Repository Settings → Security → Secret scanning → Enable

---

## Rotation Checklist

Use this checklist to track your progress:

- [ ] Ethereum wallet funds transferred to new wallet
- [ ] Crypto.com wallet migrated
- [ ] Secondary wallet migrated
- [ ] XYO wallet migrated
- [ ] Aleo private key rotated
- [ ] EOS private key rotated
- [ ] HBAR private key rotated
- [ ] KuCoin API keys revoked and regenerated
- [ ] Pionex API keys revoked and regenerated
- [ ] Crypto.com API keys revoked and regenerated
- [ ] Stripe secret key rolled
- [ ] Anthropic API key rotated
- [ ] OpenAI API key rotated
- [ ] xAI API key rotated
- [ ] HuggingFace token rotated
- [ ] OpenRouter API key rotated
- [ ] ElevenLabs API key rotated
- [ ] LangSmith API key rotated
- [ ] All GitHub PATs deleted and recreated
- [ ] Docker Hub PAT rotated
- [ ] Alchemy API key rotated
- [ ] Pinecone API key rotated
- [ ] Firebase API key rotated
- [ ] Google AI API key rotated
- [ ] Telegram bot token revoked
- [ ] Gmail app password changed
- [ ] Twitter/X access token regenerated
- [ ] SendGrid API key rotated
- [ ] ProductHunt API key rotated
- [ ] WiGLE API token rotated
- [ ] BugCrowd API token rotated
- [ ] Latitude API key rotated
- [ ] Bankwest password changed + 2FA enabled
- [ ] ATO notified of TFN exposure

---

*Generated: 2026-02-27 | Branch: claude/rotate-exposed-credentials-9Uxdt*
