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
| CodeQL | `.github/workflows/codeql.yml` | Data-flow analysis (`security-extended`). On PRs, pushes to main, and weekly |
| Agent Output Audit | `.github/workflows/agent-output-audit.yml` | Naming, comparison framing, leaks, JA/EN parity |
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
- Run `make action-pins` (shape only, no network) and `make action-pins-verify`
  (asks GitHub whether the SHA exists and whether the tag in the comment resolves
  to it). The verifying half also runs in the CI lint job, using `github.token`

> **A pin breaks in two ways: well-formed but pointing at nothing, and pointing at
> something while its comment names a different version.** Both were present here.
>
> - `github/codeql-action/upload-sarif` was pinned to `ce28f5bb`, commented
>   `# v3.28.0`, and **that commit does not exist in that repository** (the real
>   v3.28.0 is `48ab28a6`). The Scorecard workflow failed at action resolution,
>   before any step ran, on every push from the day it was added. The README badge
>   pointed at a scan that had never happened
> - `gitleaks/gitleaks-action` at `ff98106e` is v2.3.9 and the comment said
>   `# v2.3.8` (which is `f586c143`). **The pin was right and the label wrong**, so
>   nothing failed and the file described a version that was not running
>
> **Neither was visible to the checks already here.** zizmor lints workflow content,
> so an unresolvable SHA is well-formed as far as it is concerned. Renovate updates
> pins it can resolve, so a digest it cannot find is not a pin it manages. And the
> red X was indistinguishable from the Scorecard checks that genuinely depend on
> repository settings.

> **Unresolved**: the `ossf/scorecard-action` pin is v2.4.1 and the current release
> is v2.4.4. Whether to follow is left to Renovate's major/minor policy.

## Where Scorecard stands, and what is not being chased

**The score is not the goal.** Work aimed at a metric moves the number without adding a
defence. What follows records what was earned, what is deliberately left, and why — as
material for revisiting the decision rather than re-deciding it from scratch each time.

| Check | State | Decision |
|---|---|---|
| Vulnerabilities, Security-Policy, Token-Permissions, Pinned-Dependencies, Dangerous-Workflow, Dependency-Update-Tool, License, CI-Tests, Maintained, Binary-Artifacts | 10 | the result of changes with substance behind them |
| SAST | 8 | CodeQL runs on every PR. **It is a ratio over recent history**, so it climbs as commits land |
| Branch-Protection | protection is on. **The score stays `-1`** | the default `GITHUB_TOKEN` cannot read protection settings (Administration: read), and **that scope does not exist in Actions `permissions:`**. Scoring it needs a PAT in a secret passed as `repo_token`, which is manual work outside the repository. **The protection works; the metric cannot see it** |
| Code-Review | 0 | zero approved changesets. **Needs a reviewer; code cannot move it** |
| CII-Best-Practices | 0 | requires registering on bestpractices.dev, an account action outside this repository |
| Fuzzing | 0 | Scorecard counts OSS-Fuzz, ClusterFuzzLite, Go native fuzzing, and property-based testing for Haskell, JS/TS, Erlang, C#/F#. **Python's Hypothesis is not in that list.** No fuzzing harness will be built for the number |
| Contributors | 3 | counts contributors with organisational affiliation; a single-maintainer repository cannot move it |
| Packaging, Signed-Releases | `-1` | nothing is published as a package, so there is nothing to evaluate |

### Branch protection on main

| Setting | Value | Why |
|---|---|---|
| force push, branch deletion | denied | prevents rewriting public history; Scorecard's Tier 1 requirement |
| pull request required | yes, with 0 approvals | **requiring an approval would leave the sole maintainer unable to merge.** Everything already goes through a PR, so the flow is unchanged |
| required status checks | `test`, `lint`, `drift`, `pre-commit`, `gitleaks`, `Sensitive Data Scan`, `Analyze Python` | **only the ones that run on every PR.** `zizmor` and `audit` are filtered by `paths`; requiring them would leave a PR that touches neither waiting forever |
| applies to administrators | yes | without it Scorecard reads `EnforceAdmins` as false, and the protection is not really one |
| conversation resolution required | yes | — |

To remove: `gh api -X DELETE repos/<owner>/<repo>/branches/main/protection`.

**A solo merge under these settings has been observed to work** (PR #38 merged with zero
approvals), and a PR where `zizmor` does not run still reaches `mergeStateStatus: CLEAN` —
which is why it is not required.

## Adding dependencies

- **Tools that decide whether a gate passes** (ruff, bandit, cfn-lint, pytest)
  are pinned with `==` in `requirements-dev.txt`. A range lets two machines
  install different versions from the same file. Measured: with
  `cfn-lint>=0.87.0`, PATH had 1.52.1 and `.venv` had 1.52.0.
- CI installs them with `pip install -r requirements-dev.txt`. Do not name
  versions in a workflow; `check_dependency_pins.py` fails on inline installs.
- **What CI installs is the hash-pinned `requirements-ci.lock`.** Workflows call only
  `make ci-install` (`pip install --require-hashes`). Local `make dev-install` stays on
  `requirements-dev.txt`, because the lock is resolved for Python 3.12 and `.venv` may
  be newer. **`check_dependency_pins.py` is what keeps the two naming the same
  versions.** The lock is generated: `make ci-lock` (needs uv and a network).
- **`make deps-resolve` asks whether each requirements file can be installed at all.**
  There is a class of error only visible there — below.
- **Runtime dependencies use `==` as well.** `check_dependency_pins.py` sweeps every
  requirements file and fails on a range. These used to keep ranges "for edge
  devices", and that was the direct cause of the score below. Renovate proposes the
  bumps.
- `make deps-audit` asks OSV about the pinned versions. **It needs a network and its
  verdict changes without a commit here** — an advisory published overnight turns a
  green run red — so it stays out of `check` and is run before publishing.

> **A range is a supply-chain finding, not a convenience.** Scorecard's
> Vulnerabilities check scored **0, with 26 known vulnerabilities**, and the cause was
> the shape of the requirements files rather than one dangerous dependency.
>
> - **A range does not state which version runs**, so a scanner counts every advisory
>   ever filed against the package. NumPy items from 2018 were being reported against
>   `numpy>=1.26.0`
> - **The floors were genuinely stale.** `requests>=2.31.0` allowed 2.31.0, which
>   leaks `.netrc` credentials to a malicious redirect (PYSEC-2026-1872, fixed in
>   2.32.4) — and that is the `requests` used by `sensors/ontap_telemetry.py`, which
>   authenticates to ONTAP. `pyarrow>=15.0.0` predated the fixes in 17.0.0 and 23.0.1
>
> **Pinning removes the ambiguity, not the risk.** A pin records that a version was
> clean when it was written; advisories are published afterwards. Hence `make
> deps-audit`.

> **Whether a pinned combination installs is a separate question.** The first version of
> these pins paired `opencv-python-headless==4.14.0.94` with `numpy==1.26.4`, justified
> in a comment claiming OpenCV 4.x wheels need the NumPy 1.x ABI. **4.14 declares
> `numpy>=2`, so that set does not resolve** and `pip install` fails on the device.
>
> **No gate saw it.** ruff and bandit do not read requirements. `check_dependency_pins.py`
> only looked at the shape of a specifier. CI never installed these files, having its own
> list. **Nothing stood between "pinned" and "installable."** That is `make deps-resolve`,
> which asks `uv pip compile` whether the set has a solution.
>
> For the same reason `check_dependency_pins.py` now also fails when **one package is
> pinned to different versions in two files**: an edge device installs both
> `requirements.txt` and its role file, so a disagreement is decided silently by whichever
> pip ran last.

> **Open**: `.venv` is Python 3.14 while CI and the Lambda runtime are 3.12, so
> `make test` does not exercise the interpreter that ships.
> `check_dependency_pins.py` prints this as a NOTE on every run.

## Related documents

- [Quality gates](quality-gates_en.md)
- [Security design](../en/security-design.md)
