# Security Policy

## Reporting a Vulnerability

Please report suspected vulnerabilities privately by opening a GitHub security advisory for this repository or emailing the maintainers directly. Include reproduction steps, impact, and affected files.

Do not post sensitive details in public issues.

## Secrets / credentials

- Do not commit real API keys, private keys, passwords, certificates, or mnemonic phrases.
- Use environment variables for runtime secrets.
- Use `fractalmesh/.env.example` and `fractalmesh/shared/env/global.env.example` as templates only.
- If a credential is exposed, rotate it immediately at the provider and replace repository values with placeholders.
