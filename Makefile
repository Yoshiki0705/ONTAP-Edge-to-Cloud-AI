# Quality gates for edge-to-cloud-ai.
#
# This file is the single place that knows which paths get checked. CI invokes
# these targets rather than repeating the tool commands, so a path added here is
# picked up by both, and neither side can end up inspecting a different tree.
#
# Two failure modes this file is deliberately shaped against:
#
#   1. A target whose name matches a directory (security/, docs/, scripts/,
#      tests/, shared/, cloud/, edge/) is treated by make as a file that is
#      already up to date, and the recipe never runs — silently, exit 0. Every
#      target below is therefore declared in .PHONY, and
#      scripts/tests/test_makefile_phony.py fails if one is ever missed.
#   2. Bare `ruff` / `bandit` / `cfn-lint` resolve to whatever is on PATH, which
#      is not what CI installs. TOOL_* below point into .venv, and `make
#      tool-versions` prints what is actually being used.

VENV        := .venv
PY          := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
RUFF        := $(VENV)/bin/ruff
BANDIT      := $(VENV)/bin/bandit
CFN_LINT    := $(VENV)/bin/cfn-lint
PRECOMMIT   := $(VENV)/bin/pre-commit
PYTEST      := $(PY) -m pytest

# ---------------------------------------------------------------------------
# Path inventory — the single source of truth shared with CI.
# ---------------------------------------------------------------------------

# Directories pytest must collect. scripts/tests holds the gate self-tests.
#
# There is one suite per subject, in tests/. usecases/*/tests/ used to hold
# near-copies of three of these files and both sets ran, so the older assertions
# passed alongside the newer ones and nothing reported the divergence.
TEST_DIRS := \
	tests \
	scripts/tests

# Python that ships or runs: linted and scanned.
PY_DIRS := cloud edge scripts shared usecases local-demo

# CloudFormation / SAM templates.
CFN_TEMPLATES := $(wildcard cloud/*/template.yaml) $(wildcard usecases/*/template.yaml)

# Markdown subject to the agent-output rules (naming, neutrality, leaks).
MD_DIRS := docs usecases cloud cfn-params

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

venv-check: ## Fail early if the pinned toolchain is missing
	@test -x $(PY) || { echo "ERROR: $(PY) not found. Run: python3 -m venv $(VENV) && make dev-install"; exit 1; }

dev-install: venv-check ## Install pinned dev tooling into .venv
	$(PIP) install --require-virtualenv -r requirements-dev.txt

tool-versions: venv-check ## Print the versions actually in use
	@printf 'python    '; $(PY) --version
	@printf 'pytest    '; $(PYTEST) --version 2>&1 | head -1
	@printf 'ruff      '; $(RUFF) --version 2>/dev/null || echo '(missing: make dev-install)'
	@printf 'bandit    '; $(BANDIT) --version 2>/dev/null | head -1 || echo '(missing: make dev-install)'
	@printf 'cfn-lint  '; $(CFN_LINT) --version 2>/dev/null || echo '(missing: make dev-install)'

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

test: venv-check ## Run every test directory in TEST_DIRS
	$(PYTEST) $(TEST_DIRS) -q

test-verbose: venv-check ## Run every test directory with -v
	$(PYTEST) $(TEST_DIRS) -v

# ---------------------------------------------------------------------------
# Lint and security
# ---------------------------------------------------------------------------

lint: lint-py lint-cfn headings links action-pins hygiene ## Run all linters

lint-py: venv-check ## ruff over PY_DIRS
	$(RUFF) check $(PY_DIRS)

lint-cfn: venv-check ## cfn-lint over CFN_TEMPLATES
	$(CFN_LINT) $(CFN_TEMPLATES)

# --selftest runs first and on purpose. A detector whose regex has been loosened
# still exits 0 over the tree, so a green `make headings` on its own does not say
# the check can still fail. The self-test asserts both directions — that the
# sentence forms are flagged and the noun phrases are not — before the tree is
# inspected.
headings: ## Japanese section headings must be noun phrases
	@python3 scripts/check_heading_style.py --selftest >/dev/null
	@python3 scripts/check_heading_style.py

# The hooks in .pre-commit-config.yaml used to run only in the CI job, so a missing
# final newline in a generated file was invisible until a PR was opened. pre-commit
# is already pinned in requirements-dev.txt and counted as a gate tool; this target
# is what makes it reachable locally.
hygiene: venv-check ## .pre-commit-config.yaml hooks over the whole tree
	$(PRECOMMIT) run --all-files

# Relative links and anchors only: no network, so it can sit in the commit gate.
# The anchor half is the reason it exists — GitHub answers an unknown fragment
# with the top of the page, so a renamed heading breaks every link into it while
# still looking like a working link. Blocked defects are asserted in
# scripts/tests/test_link_gate.py; the first real run over this tree resolved 990
# links and reported nothing, which on its own is also what a no-op prints.
links: venv-check ## Relative Markdown links and anchors must resolve
	$(PY) scripts/check_links.py

# Not in `lint`, and not in `check`. This one leaves the repository: a red run can
# mean a host is down rather than a link being wrong, and a networked probe inside
# the commit gate is how a gate stops being read. Run it before publishing, and
# when adding a link to a sibling repository.
links-external: venv-check ## Also probe http(s) URLs (needs a network)
	$(PY) scripts/check_links.py --external

# Shape only: a 40-character SHA and a version comment. That is all this half can
# see, and it is not enough — the Scorecard workflow was pinned to a well-formed
# SHA that is not a commit in that repository, and failed at action resolution on
# every push to main from the day it was added.
action-pins: venv-check ## Actions must be pinned to a SHA with a version comment
	$(PY) scripts/check_action_pins.py

# Asks GitHub whether each SHA exists and whether the tag in the comment resolves to
# it. Networked, so it sits beside links-external rather than in `check`. A rate
# limit is reported as undetermined and does not fail: uses a token from
# GITHUB_TOKEN, GH_TOKEN or `gh auth token` when one is available.
action-pins-verify: venv-check ## Resolve every pin against GitHub (needs a network)
	$(PY) scripts/check_action_pins.py --verify

security: bandit secrets ## Static analysis and secret scan

bandit: venv-check ## bandit over PY_DIRS
	$(BANDIT) -q -r $(PY_DIRS) -c pyproject.toml

# `A && B || C` was wrong here: gitleaks exits 1 when it finds something, so the
# || branch ran and printed "skipped" over real hits while make returned 0.
# Availability and outcome are now separate statements, and a finding fails.
#
# Scope is the working tree. Full history is scanned by .github/workflows/gitleaks.yml
# (fetch-depth: 0); it reports 5 findings from one 2026-05-29 commit whose content
# has since been corrected, and history cannot be edited from a make target.
secrets: ## gitleaks over the working tree (skips only when gitleaks is absent)
	@if command -v gitleaks >/dev/null; then \
		gitleaks dir . --config .gitleaks.toml --redact --no-banner; \
	else \
		echo "NOTE: gitleaks not on PATH — install it (brew install gitleaks). CI still runs it."; \
	fi

# ---------------------------------------------------------------------------
# Drift guards — the checks that keep the gates above from going quiet
# ---------------------------------------------------------------------------

drift: venv-check ## Every guard that detects a silently-disabled gate
	$(PY) scripts/check_agent_context_budget.py
	$(PY) scripts/check_test_coverage_drift.py
	$(PY) scripts/check_git_hooks_wiring.py
	$(PY) scripts/check_dependency_pins.py
	$(PY) scripts/check_sql_interpolation.py
	$(PY) scripts/check_doc_parity.py
	$(PY) scripts/check_sunset_services.py
	$(PY) scripts/check_diagram_assets.py
	$(PY) scripts/check_verification_ledger.py
	$(PY) scripts/check_lambda_env_contract.py
	$(PY) scripts/check_cfn_params_contract.py
	$(PY) scripts/check_ontap_setup_scripts.py

# Not part of `drift`: that target holds the guards that detect a silently-disabled gate, and this
# is a content gate rather than one of those. It needs neither the AWS icon package nor draw.io --
# only the committed .drawio and .svg -- so unlike the diagram build it can run in `check`.
diagram-fonts: venv-check ## Diagram labels must clear the readability floor
	$(PY) scripts/check_diagram_fonts.py --selftest >/dev/null
	$(PY) scripts/check_diagram_fonts.py

diagram-flow: venv-check ## Diagrams must read rightwards and downwards, labels under icons
	$(PY) scripts/check_diagram_flow.py --selftest >/dev/null
	$(PY) scripts/check_diagram_flow.py
agent-config: ## Report unreachable global/workspace steering, skills and hooks
	@python3 "$$HOME/.kiro/hooks/scripts/validate_agent_config.py"

# ---------------------------------------------------------------------------

check: lint security test drift diagram-fonts diagram-flow ## Everything CI runs

precommit-install: ## Point git at .githooks for this repo
	git config core.hooksPath .githooks
	@echo "core.hooksPath -> $$(git config core.hooksPath)"

clean: ## Remove caches and build output
	rm -rf .pytest_cache .aws-sam __pycache__
	find . -name __pycache__ -type d -not -path './$(VENV)/*' -prune -exec rm -rf {} +

.PHONY: help venv-check dev-install tool-versions test test-verbose lint lint-py \
	lint-cfn headings links links-external action-pins action-pins-verify hygiene \
	security bandit secrets drift agent-config diagram-fonts diagram-flow check \
	precommit-install clean
