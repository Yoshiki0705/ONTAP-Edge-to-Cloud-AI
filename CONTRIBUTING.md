# Contributing

Thank you for your interest in contributing to this project.

## How to Contribute

1. **Issues**: Report bugs, suggest features, or ask questions via GitHub Issues.
2. **Pull Requests**: Fork the repo, create a branch, make changes, and submit a PR.
3. **Discussions**: Share your use cases, deployment experiences, or architecture ideas.

## Development Setup

```bash
git clone https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai.git
cd ontap-edge-to-cloud-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest
pytest tests/
```

## Code Standards

- Python 3.12, type hints, docstrings
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`
- All tests must pass before merge
- CloudFormation templates must pass `cfn-lint`
- No secrets or credentials in code (use environment variables)

## Documentation

- Documents are bilingual (Japanese primary, English synced)
- Both language versions must be updated together
- Code comments in English only

## Security

If you discover a security vulnerability, please report it privately via GitHub Security Advisories rather than opening a public issue.
