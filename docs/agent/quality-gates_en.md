# Quality Gates

> What each gate in this repository inspects, where it runs, and how it fails
> when it breaks. Not always-loaded context: read it when adding or changing a
> gate, or when investigating a CI failure.
>
> 日本語: [quality-gates.md](quality-gates.md)

## The Makefile is the only entry point

Path inventories live in Makefile variables (`TEST_DIRS`, `PY_DIRS`,
`CFN_TEMPLATES`) as the single source of truth. CI invokes make targets rather
than tools directly, so local runs and CI cannot inspect different trees.

```bash
make dev-install     # install the pinned tooling from requirements-dev.txt into .venv
make tool-versions   # print the versions actually in use
make check           # lint + security + test + drift (what CI runs)
```

| Target | Scope | Fails when |
|---|---|---|
| `make test` | `TEST_DIRS` | a test fails |
| `make lint-py` | `PY_DIRS` | ruff reports anything |
| `make lint-cfn` | `CFN_TEMPLATES` | cfn-lint reports anything |
| `make hygiene` | every git-tracked file | a hook in `.pre-commit-config.yaml` had to rewrite something (final newline, trailing whitespace, YAML/JSON syntax, a file over 1 MB) |
| `make bandit` | `PY_DIRS` | any finding, at any severity |
| `make secrets` | working tree, via `.gitleaks.toml` | any finding |
| `make drift` | the eleven guards below | a gate is structurally able to go quiet |
| `make agent-config` | global and workspace steering, skills, hooks | unreachable configuration |

## Drift guards

These are not gates on the code. They detect that a gate has gone quiet. All live
in `scripts/` and run from `make drift`, `.githooks/pre-commit` and CI.

| Script | What it detects |
|---|---|
| `check_agent_context_budget.py` | AGENTS.md growth, loaders carrying content, index targets missing or untracked |
| `check_test_coverage_drift.py` | a tests/ directory absent from `TEST_DIRS`, `testpaths` or the CI matrix; new same-named test files |
| `check_git_hooks_wiring.py` | `core.hooksPath` overriding `.githooks/`; a `.pre-commit-config.yaml` nothing runs |
| `check_dependency_pins.py` | ranges in `requirements-dev.txt`; CI Python version vs Lambda runtime; inline `pip install` in CI |
| `check_sql_interpolation.py` | a SQL construction site missing from `scripts/reviewed_sql_sites.txt`, and entries that no longer match code |
| `check_doc_parity.py` | heading-level sequences diverging between a JA/EN pair, **a diagram or example present in one language only** (differing fenced-block counts), one-sided files, and stale entries in `scripts/known_doc_parity_gaps.txt` |
| `check_sunset_services.py` | a document naming a service closed to new customers without a note about its status |
| `check_diagram_assets.py` | a committed icon-library file, a figure whose SVG or PNG was never re-exported, Japanese left in an English artifact |
| `check_verification_ledger.py` | the verification ledger no longer describing what ships (a model ID cited as measured has left the code, a row was added to one language only, a basis link rotted, a tier outside the borrowed vocabulary appeared) |
| `check_lambda_env_contract.py` | a template's environment variables disagreeing with what the handler reads, an override declared must-set in `usecases/handler-map.txt` left unset, a prompt that never asks for the keys the handler parses, a Lambda function absent from the map |
| `check_cfn_params_contract.py` | a parameter file disagreeing with its template (a key the template does not declare, a key besides `ParameterKey`/`ParameterValue`, a no-`Default` parameter missing or empty, a placeholder value), a parameter file matching no template, a file with no row in the `cfn-params/README.md` table |

Their self-tests are in `scripts/tests/` and run under `make test`.

## Silent failures measured in this repository

When adding a gate, check it is not repeating one of these. **Do not trust a new
gate until it has failed on an input that should fail it.**

| Symptom | What was happening |
|---|---|
| `.githooks/pre-commit` had never executed | a global `core.hooksPath` replaces the per-repository hook path outright. The author-email check and the workflow lint never ran |
| all six `.pre-commit-config.yaml` hooks ran nowhere | `pre-commit` CLI not installed, `.git/hooks/` empty, no workflow calling `pre-commit run` |
| gitleaks default rules were off for 700 KB | `[allowlist] paths` listed `*.md`, `*.sh`, workflows and infrastructure templates. A gitleaks allowlist `paths` entry **skips the file**, so silencing two custom rules also disabled AWS-key, GitHub-token and private-key detection. `matchCondition = "AND"` does not narrow this |
| gitleaks reported 218 findings and make succeeded | `command -v gitleaks && gitleaks detect ... \|\| echo "skipped"`. gitleaks exits 1 on a finding, so the `\|\|` branch ran, printed "skipped", and make returned 0 |
| `# nosec` had no effect | bandit reads the comment on the **reported line only**. Placed a line above, the run shows `Total lines skipped (#nosec): 0` |
| A newly added parity gate never compared one of the pairs | it walked `*_en.md` only, so `edge/soracom/README.md` ↔ `README_ja.md` — the reversed suffix — was out of scope. Not walking a path does not show up in the output |
| A newly added sunset gate reported one of two identical defects | `maintenance` was in the list of status phrases as a bare word, so a document containing `predictive maintenance` passed. 7 of 60 documents carry that word |
| `pytest` and CI checked different sets | no `testpaths`. `scripts/tests/` was in neither, and `edge/raspberry-pi/camera/test_prompt.py` is a CLI script with zero test functions that looked like a suite |

## Adding a gate

1. Add the target to the Makefile and **put it in `.PHONY`**. If a directory of
   the same name exists, make reports "up to date" and skips the recipe.
   `scripts/tests/test_makefile_phony.py` fails on a missing declaration.
2. Put paths in a Makefile variable, not inside the recipe.
3. Call the make target from CI. Do not name tools in the workflow.
4. **Confirm it fails on a broken input.** Plant something that should be caught
   and run it: `printf 'TOKEN="ghp_..."' > tests/_probe.py && make secrets`
5. When adding a suppression (`# nosec`, `# noqa`, an allowlist entry), run a
   negative control afterwards to check it did not silence more than intended.

## Related documents

- [Supply-chain security](supply-chain-security_en.md) — Actions pinning, adding dependencies
- [Reference-doc quality bar](reference-doc-quality_en.md)
- [Security design](../en/security-design.md) — includes the OT/IT boundary
- [TESTING_en.md](../../TESTING_en.md) — what the tests cover and how to run them
