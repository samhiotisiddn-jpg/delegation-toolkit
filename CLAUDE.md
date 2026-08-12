# Delegation Toolkit

FractalMesh deployment toolkit containing deployment scripts, agent configurations, and supporting materials.

## Structure

```
delegation-toolkit/
├── fractalmesh/              # Core FractalMesh system files
├── fractalmesh-safe-deploy*.sh  # Deployment scripts
├── sovereign_node*.sh        # Node initialization scripts
├── .env.example              # Required environment variable template
├── scripts/
│   └── verify-no-secrets.sh  # Pre-commit secret scanner
├── .github/workflows/ci.yml  # CI with secret-scan and shellcheck
├── docs/
│   ├── DEPLOYMENT.md         # Safe deployment guide
│   └── safe-payment-webhook-template.md  # Defensive webhook blueprint
├── START_HERE.txt            # Getting started guide
├── PROVIDER_GUIDE.txt        # AI provider configuration
├── SECURITY.md               # Vulnerability reporting and secret rules
├── CONTRIBUTING.md           # Contribution guidelines
├── README.md                 # Repository overview
└── guidelines/               # Operational guidelines
```

## Getting Started

1. Read `START_HERE.txt` for setup instructions.
2. Read `PROVIDER_GUIDE.txt` for API provider configuration.
3. Copy `.env.example` to your local config directory and fill in values.
4. Review `docs/DEPLOYMENT.md` before running any deployment script.

## Deployment

```bash
# Review the deployment script before running
cat "fractalmesh-safe-deploy (1).sh"

# Run deployment (review contents first)
bash "fractalmesh-safe-deploy (1).sh"
```

## Security

- Never commit API keys, private keys, or credentials to this repository.
- Store all credentials in environment variables or a secrets manager.
- Rotate any credentials that may have been exposed immediately.
- Run `bash scripts/verify-no-secrets.sh` before committing.
- See `SECURITY.md`, `CONTRIBUTING.md`, and `CREDENTIAL_ROTATION_GUIDE.md` for full guidance.

## Scope

This project focuses on safe deployment tooling, defensive security, and operational documentation. Proposals for dark-web automation, credential harvesting, autonomous financial execution, or unsupervised offensive capabilities are out of scope.
