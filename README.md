# delegation-toolkit

FractalMesh deployment toolkit containing deployment scripts, agent configurations, and supporting materials.

## Secrets / Credentials

All API keys, passwords, and tokens **must** be stored as environment variables — never committed to source code.

```bash
cp fractalmesh/.env.example fractalmesh/.env
# Fill in real values in fractalmesh/.env (never commit this file)
```

See `fractalmesh/.env.example` for required variables and `SECURITY.md` for rotation procedures.

## Security

For vulnerability reporting and security automation details, see [SECURITY.md](SECURITY.md).

[![Security Scan](https://github.com/samhiotisiddn-jpg/delegation-toolkit/actions/workflows/security.yml/badge.svg)](https://github.com/samhiotisiddn-jpg/delegation-toolkit/actions/workflows/security.yml)
[![CI](https://github.com/samhiotisiddn-jpg/delegation-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/samhiotisiddn-jpg/delegation-toolkit/actions/workflows/ci.yml)
