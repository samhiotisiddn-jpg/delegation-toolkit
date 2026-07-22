# Delegation Toolkit

FractalMesh deployment toolkit containing deployment scripts, agent configurations, and supporting materials.

## Structure

```
delegation-toolkit/
├── fractalmesh/              # Core FractalMesh system files
├── fractalmesh-safe-deploy*.sh  # Deployment scripts
├── sovereign_node*.sh        # Node initialization scripts
├── START_HERE.txt            # Getting started guide
├── README.md                 # Repository overview
└── guidelines/               # Operational guidelines
```

## Getting Started

Read `START_HERE.txt` first for setup instructions, then `PROVIDER_GUIDE.txt` for API provider configuration.

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
- See `CREDENTIAL_ROTATION_GUIDE.md` for rotation procedures.
