# AGENTS.md

> Edge-to-cloud data collection, analytics, and AI pipelines from Raspberry Pi and SORACOM to AWS services

## Project Overview

This repository provides reference architectures for connecting IoT/edge devices (Raspberry Pi, SORACOM cellular gateways) to AWS analytics and AI services (Athena, Glue, SageMaker, Bedrock, Rekognition).

## Build & Test Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Lint CloudFormation
cfn-lint cloud/**/*.yaml
```

## Coding Conventions

- Python 3.12 for edge scripts and Lambda functions
- TypeScript for CDK constructs
- Structured JSON logging
- Type hints required for all Python functions

## Supply-Chain Security

### Automated Security Workflows

| Workflow | File | Purpose |
|----------|------|---------|
| zizmor | `.github/workflows/zizmor.yml` | GitHub Actions security linting |
| gitleaks | `.github/workflows/gitleaks.yml` | Secret detection — custom rules in `.gitleaks.toml` |
| OpenSSF Scorecard | `.github/workflows/scorecard.yml` | Automated security health scoring |

### Local Security Checks

```bash
# Pre-commit hook runs automatically (via .githooks/pre-commit):
#   1. Author email verification
#   2. gitleaks secret scanning (staged files)
#   3. zizmor lint (if workflow files changed)

# Manual verification
gitleaks detect --config .gitleaks.toml --no-git --source .
zizmor .github/workflows/
```

### Actions Pinning Policy

- All third-party Actions MUST be pinned to SHA hashes: `uses: owner/action@<sha> # vX.Y.Z`
- `actions/checkout` must set `persist-credentials: false`
- Verify with `zizmor .github/workflows/` before committing workflow changes
