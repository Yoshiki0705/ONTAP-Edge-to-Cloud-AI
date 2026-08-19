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
python3 -m venv .venv
make dev-install          # pinned tooling into .venv
make precommit-install    # point core.hooksPath at .githooks
make check                # lint + security + test + drift, same as CI
```

`pytest tests/` runs a subset. `make test` runs every directory in the
Makefile's `TEST_DIRS`, which is the list CI uses. Do not invoke `ruff`,
`bandit`, `cfn-lint` or `pytest` directly for a final check: a bare command
resolves to whatever is on PATH, which is not the version pinned in
`requirements-dev.txt`.

## Code Standards

- Python 3.12, type hints, docstrings
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`
- `make check` must pass before merge
- No secrets or credentials in code (use environment variables)
- Validate any identifier that arrives in an event before it reaches a path, an
  S3 key or a SQL statement — see `cloud/iot_ingestion/identifiers.py`
- A new query has to be classified in `scripts/reviewed_sql_sites.txt`; the
  build fails on a construction site that is not listed there

## Documentation

- Documents are bilingual (Japanese primary, English synced)
- Both language versions must be updated together
- Code comments in English only

## Security

If you discover a security vulnerability, please report it privately via GitHub Security Advisories rather than opening a public issue.
