# Supply-Chain Security

> Read when adding or changing a GitHub Actions workflow, or adding a dependency.
>
> 日本語: [supply-chain-security.md](supply-chain-security.md)

## Automated checks

| Workflow | File | Purpose |
|---|---|---|
| zizmor | `.github/workflows/zizmor.yml` | Actions security lint (fires only on `paths: .github/workflows/**`) |
| gitleaks | `.github/workflows/gitleaks.yml` | Secret detection over full history (`fetch-depth: 0`) |
| OpenSSF Scorecard | `.github/workflows/scorecard.yml` | Security health scoring |
| Agent Output Audit | `.github/workflows/agent-output-audit.yml` | Naming, vendor neutrality, leaks, JA/EN parity |
| Security & Privacy | `.github/workflows/security-check.yml` | Paths that must not be tracked, real IPs, persona names |

## Local

```bash
make precommit-install   # point core.hooksPath at .githooks (once)
make secrets             # gitleaks over the working tree
zizmor .github/workflows/
```

`.githooks/pre-commit` delegates to the global hook before running its own
checks. `core.hooksPath` holds a single value, so pointing it at the repository
would otherwise stop the global checks (staged-path blocking for `.kiro/`,
`.env`, keys). The delegation avoids trading one gate for the other.

> **On history**: `make secrets` inspects the working tree; history is covered by
> `gitleaks.yml`. Five findings remain in one 2026-05-29 commit (the then-current
> `.githooks/pre-commit` and `tests/test_ontap_e2e.py`); the content has since
> been corrected in both files. Rewriting history is not something a make target
> should do.

## Actions pinning

- Pin third-party Actions to a SHA: `uses: owner/action@<sha> # vX.Y.Z`
- Set `persist-credentials: false` on `actions/checkout`
- Run `zizmor .github/workflows/` before committing a workflow change

## Adding dependencies

- **Tools that decide whether a gate passes** (ruff, bandit, cfn-lint, pytest)
  are pinned with `==` in `requirements-dev.txt`. A range lets two machines
  install different versions from the same file. Measured: with
  `cfn-lint>=0.87.0`, PATH had 1.52.1 and `.venv` had 1.52.0.
- CI installs them with `pip install -r requirements-dev.txt`. Do not name
  versions in a workflow; `check_dependency_pins.py` fails on inline installs.
- Runtime dependencies in `requirements.txt` keep ranges for edge devices. A
  production artifact should carry a separate lock file.

> **Open**: `.venv` is Python 3.14 while CI and the Lambda runtime are 3.12, so
> `make test` does not exercise the interpreter that ships.
> `check_dependency_pins.py` prints this as a NOTE on every run.

## Related documents

- [Quality gates](quality-gates_en.md)
- [Security design](../en/security-design.md)
