# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| main    | ✅ Yes    |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

To report a security vulnerability, please email the maintainer directly or use
[GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
for this repository.

Include as much detail as possible:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We aim to acknowledge reports within **72 hours** and provide a fix or mitigation
within **14 days** for critical issues.

## Secrets / Credentials

All credentials and API keys **must** be stored as environment variables — never
hardcoded in source code.

Copy `fractalmesh/.env.example` to `fractalmesh/.env` and fill in real values:

```bash
cp fractalmesh/.env.example fractalmesh/.env
# edit fractalmesh/.env with your actual keys
```

Required environment variables (see `.env.example` for full list):

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role JWT |
| `STRIPE_SECRET_KEY` | Stripe secret key (`sk_live_…` or `sk_test_…`) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret (`whsec_…`) |
| `XAI_API_KEY` | xAI / Grok API key |
| `NGROK_AUTHTOKEN` | ngrok tunnel auth token |

If you believe a credential has been exposed, rotate it immediately at the
relevant provider dashboard and update your `.env` file.

## Security Automation

This repository uses:
- **CodeQL** — static analysis for Python, runs on every push/PR.
- **Bandit** — Python security linter, runs on every push/PR.
- **pip-audit** — dependency vulnerability scanner, runs on every push/PR.
- **Dependabot** — automated dependency updates (weekly).
