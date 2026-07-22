# Security Policy

## Supported Versions
Use the latest default branch.

## Reporting a Vulnerability
Please report vulnerabilities privately via GitHub Security Advisories (preferred) or repository contact channel.
Do not open public issues for sensitive vulnerabilities.

## Secret Handling
- Never commit API keys, wallet secrets, or private certificates.
- Use environment variables and a managed secrets vault.
- Rotate credentials immediately on exposure.

## Secure Development Baseline
- PR review required
- CI checks required
- Dependency and secret scanning enabled
