# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it privately.

1. Open a **private vulnerability report** via GitHub: [Security Advisories](https://github.com/samhiotisiddn-jpg/delegation-toolkit/security/advisories/new).
2. Do not open a public issue or pull request that discloses the vulnerability.
3. Provide a clear description, reproduction steps, and impact assessment.

We aim to acknowledge reports within 72 hours and ship fixes within 14 days for critical issues.

## Hardcoded Secrets

This repository must never contain:

- API keys or tokens (`sk_live_*`, `sk-ant-*`, `gsk_*`, `xai-*`, `hf_*`, etc.)
- Private keys or seed phrases
- Database passwords or connection strings
- Webhook signing secrets

Use environment variables or a secrets manager instead. See `.env.example` for the required variables.

## Local Development

1. Copy `.env.example` to `.env` and fill in values.
2. Ensure `.env` is ignored by Git.
3. Run `bash scripts/verify-no-secrets.sh` before each commit.
4. Use test/sandbox credentials for development.

## Incident Response (template)

If a secret is exposed:

1. Revoke the exposed credential at the provider immediately.
2. Audit logs and rotate any credentials that may have been impacted.
3. Update `.env` and any deployment secrets.
4. Document the incident and remediate root cause.

## Supported Versions

| Version | Supported |
| --- | --- |
| `main` branch | Yes |
| Older tags | Best effort |

---

*This project operates under a defensive security model. Offensive capabilities, dark-web integration, credential harvesting, and unsupervised financial automation are out of scope.*
