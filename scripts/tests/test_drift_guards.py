"""Self-tests for the drift guards.

Why these exist
---------------
A guard that has never failed is indistinguishable from a guard that cannot fail.
Each guard here is exercised in three states:

  allow — a healthy tree: exit 0
  warn  — a condition worth saying out loud that is not a failure: exit 0 with a
          NOTE on stdout
  block — a tree with the defect the guard exists for: exit 1, with the defect
          named in the message

The guards resolve their target from `Path(__file__).parents[1]`, so a test builds
a synthetic repository, copies the real script into `<fixture>/scripts/`, and runs
it there. That exercises the file as shipped rather than a re-implementation, and
it means a guard cannot be tested by breaking this repository.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"

GUARDS = [
    "check_agent_context_budget.py",
    "check_dependency_pins.py",
    "check_diagram_assets.py",
    "check_doc_parity.py",
    "check_git_hooks_wiring.py",
    "check_sql_interpolation.py",
    "check_sunset_services.py",
    "check_test_coverage_drift.py",
]


def run_guard(root: Path, name: str) -> subprocess.CompletedProcess[str]:
    """Copy a guard into the fixture repository and run it there."""
    target_scripts = root / "scripts"
    target_scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPTS / name, target_scripts / name)
    return subprocess.run(
        [sys.executable, str(target_scripts / name)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def git_init(root: Path, track: list[str] | None = None) -> None:
    """A fixture repository with an actual index, since the guards ask git."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    for path in track or []:
        subprocess.run(["git", "add", "-N", path], cwd=root, check=True)


# ---------------------------------------------------------------------------
# Every guard must be runnable and must fail loudly on an empty tree rather than
# passing vacuously.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", GUARDS)
def test_guard_exists_and_is_executable_python(name):
    path = SCRIPTS / name
    assert path.is_file(), f"{name} is referenced by make drift but does not exist"
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


@pytest.mark.parametrize("name", GUARDS)
def test_guard_runs_against_this_repository(name):
    """Whatever the verdict, a guard must not crash on the real tree."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / name)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), (
        f"{name} exited {result.returncode}; guards return 0 (allow) or 1 (block).\n"
        f"stderr: {result.stderr}"
    )
    assert "Traceback" not in result.stderr, f"{name} crashed:\n{result.stderr}"


# ---------------------------------------------------------------------------
# check_agent_context_budget.py
# ---------------------------------------------------------------------------


def _agent_context_fixture(root: Path, agents_body: str, loader_body: str | None) -> None:
    (root / "docs" / "agent").mkdir(parents=True)
    (root / "docs" / "agent" / "quality-gates.md").write_text("# Quality gates\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(agents_body, encoding="utf-8")
    tracked = ["AGENTS.md", "docs/agent/quality-gates.md"]
    if loader_body is not None:
        steering = root / ".kiro" / "steering"
        steering.mkdir(parents=True)
        (steering / "loader-quality-gates.md").write_text(loader_body, encoding="utf-8")
    git_init(root, tracked)


HEALTHY_AGENTS = (
    "# AGENTS.md\n\nAlways-true rules.\n\n"
    "| Read when | Document |\n|---|---|\n"
    "| Changing a gate | [docs/agent/quality-gates.md](docs/agent/quality-gates.md) |\n"
)

HEALTHY_LOADER = (
    "---\ninclusion: auto\nname: quality-gates\n"
    "description: When changing a gate.\n---\n\n"
    "See [docs/agent/quality-gates.md](../../docs/agent/quality-gates.md).\n"
)


def test_context_budget_allows_a_healthy_tree(tmp_path):
    _agent_context_fixture(tmp_path, HEALTHY_AGENTS, HEALTHY_LOADER)
    result = run_guard(tmp_path, "check_agent_context_budget.py")
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_context_budget_blocks_oversized_agents_md(tmp_path):
    bloated = HEALTHY_AGENTS + ("Pitfalls table row.\n" * 400)
    _agent_context_fixture(tmp_path, bloated, HEALTHY_LOADER)
    result = run_guard(tmp_path, "check_agent_context_budget.py")
    assert result.returncode == 1
    assert "read on every turn" in result.stderr


def test_context_budget_blocks_a_loader_carrying_content(tmp_path):
    """Content in .kiro/ is invisible to anyone cloning the repository."""
    fat_loader = (
        "---\ninclusion: auto\nname: quality-gates\ndescription: When changing a gate.\n---\n\n"
        "See [docs/agent/quality-gates.md](../../docs/agent/quality-gates.md).\n\n"
        + "Procedure step that belongs in a tracked document.\n" * 30
    )
    _agent_context_fixture(tmp_path, HEALTHY_AGENTS, fat_loader)
    result = run_guard(tmp_path, "check_agent_context_budget.py")
    assert result.returncode == 1
    assert "gitignored" in result.stderr or "does not carry the content" in result.stderr


def test_context_budget_blocks_auto_inclusion_without_name(tmp_path):
    """The failure mode with no error message: Kiro never registers the file."""
    nameless = (
        "---\ninclusion: auto\ndescription: When changing a gate.\n---\n\n"
        "See [docs/agent/quality-gates.md](../../docs/agent/quality-gates.md).\n"
    )
    _agent_context_fixture(tmp_path, HEALTHY_AGENTS, nameless)
    result = run_guard(tmp_path, "check_agent_context_budget.py")
    assert result.returncode == 1
    assert "never read" in result.stderr


def test_context_budget_blocks_a_loader_pointing_at_nothing(tmp_path):
    broken = (
        "---\ninclusion: auto\nname: quality-gates\ndescription: When changing a gate.\n---\n\n"
        "See [docs/agent/moved-away.md](../../docs/agent/moved-away.md).\n"
    )
    _agent_context_fixture(tmp_path, HEALTHY_AGENTS, broken)
    result = run_guard(tmp_path, "check_agent_context_budget.py")
    assert result.returncode == 1
    assert "does not exist" in result.stderr


def test_context_budget_blocks_an_untracked_index_target(tmp_path):
    """A doc git does not track is absent from the published repository."""
    (tmp_path / "docs" / "agent").mkdir(parents=True)
    (tmp_path / "docs" / "agent" / "quality-gates.md").write_text("# QG\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(HEALTHY_AGENTS, encoding="utf-8")
    git_init(tmp_path, ["AGENTS.md"])  # deliberately not the doc
    result = run_guard(tmp_path, "check_agent_context_budget.py")
    assert result.returncode == 1
    assert "does not track" in result.stderr


# ---------------------------------------------------------------------------
# check_git_hooks_wiring.py
# ---------------------------------------------------------------------------


def test_hooks_wiring_allows_repo_hooks_path(tmp_path):
    (tmp_path / ".githooks").mkdir()
    (tmp_path / ".githooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    git_init(tmp_path)
    subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=tmp_path, check=True)
    result = run_guard(tmp_path, "check_git_hooks_wiring.py")
    assert result.returncode == 0, result.stderr


def test_hooks_wiring_blocks_an_overriding_hooks_path(tmp_path):
    """The measured defect: a global core.hooksPath replaces .githooks/ entirely."""
    (tmp_path / ".githooks").mkdir()
    (tmp_path / ".githooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    git_init(tmp_path)
    subprocess.run(["git", "config", "core.hooksPath", str(elsewhere)], cwd=tmp_path, check=True)
    result = run_guard(tmp_path, "check_git_hooks_wiring.py")
    assert result.returncode == 1
    assert "never execute" in result.stderr


def test_hooks_wiring_blocks_a_precommit_config_nothing_runs(tmp_path):
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    git_init(tmp_path)
    result = run_guard(tmp_path, "check_git_hooks_wiring.py")
    assert result.returncode == 1
    assert "executes nowhere" in result.stderr or "no pre-commit hook" in result.stderr


def test_hooks_wiring_blocks_a_dangling_agents_reference(tmp_path):
    (tmp_path / "AGENTS.md").write_text("We run .gitleaks.toml on commit.\n", encoding="utf-8")
    git_init(tmp_path)
    result = run_guard(tmp_path, "check_git_hooks_wiring.py")
    assert result.returncode == 1
    assert "does not exist" in result.stderr


# ---------------------------------------------------------------------------
# check_dependency_pins.py
# ---------------------------------------------------------------------------


def _pins_fixture(root: Path, requirements: str, runtime: str, ci_python: str) -> None:
    (root / "requirements-dev.txt").write_text(requirements, encoding="utf-8")
    template_dir = root / "cloud" / "svc"
    template_dir.mkdir(parents=True)
    (template_dir / "template.yaml").write_text(
        f"Resources:\n  Fn:\n    Properties:\n      Runtime: python{runtime}\n", encoding="utf-8"
    )
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "test.yml").write_text(
        "jobs:\n  t:\n    steps:\n"
        f"      - uses: actions/setup-python@v5\n        with:\n          python-version: \"{ci_python}\"\n"
        "      - run: make test\n",
        encoding="utf-8",
    )


def _gate_tools() -> list[str]:
    """Read GATE_TOOLS from the guard rather than restating it here.

    A hardcoded list drifted the moment pre-commit was added to the guard: the
    fixture still pinned four tools, the guard wanted five, and two tests failed
    in CI on a change that had nothing to do with them. Deriving the fixture means
    adding a gate tool cannot break these tests.
    """
    source = (SCRIPTS / "check_dependency_pins.py").read_text(encoding="utf-8")
    match = re.search(r"^GATE_TOOLS\s*=\s*\{(.*?)\}", source, re.S | re.M)
    assert match, "GATE_TOOLS not found in check_dependency_pins.py"
    tools = re.findall(r'"([^"]+)"', match.group(1))
    assert tools, "GATE_TOOLS parsed to zero entries"
    return sorted(tools)


# Every gate tool, pinned. Versions are arbitrary; only the `==` matters here.
PINNED = "".join(f"{tool}==1.0.0\n" for tool in _gate_tools())


def test_pins_allow_exact_pins_and_matching_python(tmp_path):
    _pins_fixture(tmp_path, PINNED, "3.12", "3.12")
    result = run_guard(tmp_path, "check_dependency_pins.py")
    assert result.returncode == 0, result.stderr


def test_pins_warn_when_the_local_interpreter_differs(tmp_path):
    """Warn tier: not the gate, but the usual reason local and CI disagree."""
    local = f"{sys.version_info.major}.{sys.version_info.minor}"
    other = "3.9" if local != "3.9" else "3.8"
    _pins_fixture(tmp_path, PINNED, other, other)
    result = run_guard(tmp_path, "check_dependency_pins.py")
    assert result.returncode == 0, result.stderr
    assert "NOTE:" in result.stdout
    assert "not exercising the deployed version" in result.stdout


def test_pins_block_a_range(tmp_path):
    ranged = PINNED.replace("cfn-lint==1.0.0", "cfn-lint>=0.87.0")
    assert ranged != PINNED, "the substitution did not apply; the fixture format changed"
    _pins_fixture(tmp_path, ranged, "3.12", "3.12")
    result = run_guard(tmp_path, "check_dependency_pins.py")
    assert result.returncode == 1
    assert "Use == so local and CI resolve to the same build" in result.stderr


def test_pins_block_an_unpinned_gate_tool(tmp_path):
    _pins_fixture(tmp_path, "pytest==9.1.1\n", "3.12", "3.12")
    result = run_guard(tmp_path, "check_dependency_pins.py")
    assert result.returncode == 1
    assert "is not pinned" in result.stderr


def test_pins_block_ci_python_that_never_runs_the_code(tmp_path):
    _pins_fixture(tmp_path, PINNED, "3.12", "3.9")
    result = run_guard(tmp_path, "check_dependency_pins.py")
    assert result.returncode == 1
    assert "never runs" in result.stderr


def test_pins_block_inline_pip_install_in_ci(tmp_path):
    _pins_fixture(tmp_path, PINNED, "3.12", "3.12")
    workflow = tmp_path / ".github" / "workflows" / "test.yml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8") + "      - run: pip install cfn-lint\n",
        encoding="utf-8",
    )
    result = run_guard(tmp_path, "check_dependency_pins.py")
    assert result.returncode == 1
    assert "installs" in result.stderr and "inline" in result.stderr


# ---------------------------------------------------------------------------
# check_sql_interpolation.py
# ---------------------------------------------------------------------------


def _sql_fixture(root: Path, source: str, reviewed: str, filename: str = "query.py") -> None:
    (root / "cloud").mkdir(parents=True, exist_ok=True)
    (root / "cloud" / filename).write_text(source, encoding="utf-8")
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "reviewed_sql_sites.txt").write_text(reviewed, encoding="utf-8")


INTERPOLATED_SQL = (
    "import boto3\n"
    "client = boto3.client('athena')\n"
    "def run(event):\n"
    "    q = 'SELECT * FROM t WHERE d = {}'.format(event['device_id'])\n"
    "    return client.start_query_execution(QueryString=q)\n"
)


def test_sql_sweep_allows_a_reviewed_site(tmp_path):
    _sql_fixture(tmp_path, INTERPOLATED_SQL, "cloud/query.py | DATA. Validated upstream.\n")
    result = run_guard(tmp_path, "check_sql_interpolation.py")
    assert result.returncode == 0, result.stderr
    assert "all reviewed" in result.stdout


def test_sql_sweep_blocks_an_unreviewed_site(tmp_path):
    """bandit reports neither a .format() template nor an executed event field."""
    _sql_fixture(tmp_path, INTERPOLATED_SQL, "# nothing reviewed yet\n")
    result = run_guard(tmp_path, "check_sql_interpolation.py")
    assert result.returncode == 1
    assert "cloud/query.py" in result.stderr


def test_sql_sweep_blocks_a_stale_entry(tmp_path):
    """A list that no longer describes the code stops being evidence of a sweep."""
    _sql_fixture(
        tmp_path,
        "# no SQL here at all\n",
        "cloud/removed.py | SAFE. Parameterised.\n",
    )
    result = run_guard(tmp_path, "check_sql_interpolation.py")
    assert result.returncode == 1
    assert "no longer build SQL" in result.stderr


def test_sql_sweep_blocks_when_it_finds_nothing_but_sql_is_executed(tmp_path):
    """Guarding the guard: silence must not be reported as cleanliness.

    The statement spans lines with the keyword, the interpolation and the call
    each on their own, which is what defeated the first per-line version.
    """
    (tmp_path / "cloud").mkdir(parents=True)
    (tmp_path / "cloud" / "spread.sh").write_text(
        "clickhouse-client --query \"\n"
        "  INSERT INTO t\n"
        "  SELECT *\n"
        "  FROM s\n"
        "\"\n",
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "reviewed_sql_sites.txt").write_text("# empty\n", encoding="utf-8")
    result = run_guard(tmp_path, "check_sql_interpolation.py")
    # Either it reports the site, or it reports that it went blind. Not "OK".
    assert result.returncode == 1
    assert "OK" not in result.stdout


# ---------------------------------------------------------------------------
# check_test_coverage_drift.py
# ---------------------------------------------------------------------------


def _coverage_fixture(root: Path, test_dirs: list[str], testpaths: list[str], matrix: list[str]) -> None:
    joined = " \\\n\t".join(test_dirs)
    (root / "Makefile").write_text(
        f"TEST_DIRS := \\\n\t{joined}\n\ntest:\n\tpytest $(TEST_DIRS)\n\n.PHONY: test\n",
        encoding="utf-8",
    )
    paths = ",\n    ".join(f'"{p}"' for p in testpaths)
    (root / "pyproject.toml").write_text(
        f"[tool.pytest.ini_options]\ntestpaths = [\n    {paths},\n]\n", encoding="utf-8"
    )
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    matrix_line = f"        usecase: [{', '.join(matrix)}]\n" if matrix else ""
    (workflows / "test.yml").write_text(
        "jobs:\n  t:\n    strategy:\n      matrix:\n" + matrix_line +
        "    steps:\n      - run: make test\n",
        encoding="utf-8",
    )
    for directory in set(test_dirs) | set(testpaths):
        path = root / directory
        path.mkdir(parents=True, exist_ok=True)
        (path / f"test_{path.name}_sample.py").write_text(
            "def test_ok():\n    assert True\n", encoding="utf-8"
        )


def test_coverage_allows_agreeing_inventories(tmp_path):
    _coverage_fixture(tmp_path, ["tests"], ["tests"], [])
    git_init(tmp_path)
    subprocess.run(["git", "add", "-N", "."], cwd=tmp_path, check=True)
    result = run_guard(tmp_path, "check_test_coverage_drift.py")
    assert result.returncode == 0, result.stderr


def test_coverage_blocks_a_directory_missing_from_the_makefile(tmp_path):
    _coverage_fixture(tmp_path, ["tests"], ["tests"], [])
    orphan = tmp_path / "scripts" / "tests"
    orphan.mkdir(parents=True, exist_ok=True)
    (orphan / "test_orphan.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    git_init(tmp_path)
    subprocess.run(["git", "add", "-N", "."], cwd=tmp_path, check=True)
    result = run_guard(tmp_path, "check_test_coverage_drift.py")
    assert result.returncode == 1
    assert "not in Makefile TEST_DIRS" in result.stderr


def test_coverage_blocks_disagreeing_testpaths(tmp_path):
    _coverage_fixture(tmp_path, ["tests", "extra"], ["tests"], [])
    git_init(tmp_path)
    subprocess.run(["git", "add", "-N", "."], cwd=tmp_path, check=True)
    result = run_guard(tmp_path, "check_test_coverage_drift.py")
    assert result.returncode == 1
    assert "different set" in result.stderr


def test_coverage_blocks_a_usecase_absent_from_the_ci_matrix(tmp_path):
    _coverage_fixture(tmp_path, ["tests"], ["tests"], ["listed"])
    for name in ("listed", "forgotten"):
        directory = tmp_path / "usecases" / name / "tests"
        directory.mkdir(parents=True)
        (directory / f"test_{name}.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    git_init(tmp_path)
    subprocess.run(["git", "add", "-N", "."], cwd=tmp_path, check=True)
    result = run_guard(tmp_path, "check_test_coverage_drift.py")
    assert result.returncode == 1
    assert "forgotten" in result.stderr

def test_coverage_blocks_an_untracked_test_file(tmp_path):
    """CI checks out the repository; an uncommitted test cannot run there."""
    _coverage_fixture(tmp_path, ["tests"], ["tests"], [])
    git_init(tmp_path)
    subprocess.run(["git", "add", "-N", "."], cwd=tmp_path, check=True)
    (tmp_path / "tests" / "test_never_committed.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    result = run_guard(tmp_path, "check_test_coverage_drift.py")
    assert result.returncode == 1
    assert "git does not track" in result.stderr


def test_coverage_blocks_a_new_duplicate_basename(tmp_path):
    _coverage_fixture(tmp_path, ["tests", "other"], ["tests", "other"], [])
    shutil.copy2(tmp_path / "tests" / "test_tests_sample.py", tmp_path / "other" / "test_tests_sample.py")
    git_init(tmp_path)
    subprocess.run(["git", "add", "-N", "."], cwd=tmp_path, check=True)
    result = run_guard(tmp_path, "check_test_coverage_drift.py")
    assert result.returncode == 1
    assert "drift apart" in result.stderr


def test_coverage_blocks_when_ci_does_not_call_make(tmp_path):
    _coverage_fixture(tmp_path, ["tests"], ["tests"], [])
    workflow = tmp_path / ".github" / "workflows" / "test.yml"
    workflow.write_text(workflow.read_text(encoding="utf-8").replace("make test", "pytest tests/"), encoding="utf-8")
    git_init(tmp_path)
    subprocess.run(["git", "add", "-N", "."], cwd=tmp_path, check=True)
    result = run_guard(tmp_path, "check_test_coverage_drift.py")
    assert result.returncode == 1
    assert "does not invoke a make target" in result.stderr


def test_coverage_blocks_a_test_named_file_with_no_tests_being_counted(tmp_path):
    """A CLI script named test_*.py must not be treated as a suite.

    edge/raspberry-pi/camera/test_prompt.py is one: zero test functions, imports
    boto3 at module scope. Counting it would demand coverage that is not there.
    """
    _coverage_fixture(tmp_path, ["tests"], ["tests"], [])
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "test_prompt.py").write_text(
        '"""CLI helper, not a suite."""\nimport argparse\n\ndef main():\n    pass\n',
        encoding="utf-8",
    )
    git_init(tmp_path)
    subprocess.run(["git", "add", "-N", "."], cwd=tmp_path, check=True)
    result = run_guard(tmp_path, "check_test_coverage_drift.py")
    assert result.returncode == 0, (
        "a test_*.py file with no test functions was treated as an unreachable "
        f"test directory:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# check_doc_parity.py
# ---------------------------------------------------------------------------


def _parity_fixture(
    root: Path,
    ja: str | None,
    en: str | None,
    known: str | None = None,
    name: str = "guide.md",
) -> None:
    (root / "docs" / "ja").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "en").mkdir(parents=True, exist_ok=True)
    if ja is not None:
        (root / "docs" / "ja" / name).write_text(ja, encoding="utf-8")
    if en is not None:
        (root / "docs" / "en" / name).write_text(en, encoding="utf-8")
    if known is not None:
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "scripts" / "known_doc_parity_gaps.txt").write_text(known, encoding="utf-8")


MATCHING_JA = "# 題\n\n## 概要\n\n### 詳細\n\n## まとめ\n"
MATCHING_EN = "# Title\n\n## Overview\n\n### Details\n\n## Summary\n"


def test_parity_allows_a_matching_pair(tmp_path):
    _parity_fixture(tmp_path, MATCHING_JA, MATCHING_EN)
    result = run_guard(tmp_path, "check_doc_parity.py")
    assert result.returncode == 0, result.stderr
    assert "doc parity: OK" in result.stdout


def test_parity_blocks_a_missing_subsection(tmp_path):
    """The defect measured in this repository: a `###` present in one language only."""
    _parity_fixture(tmp_path, MATCHING_JA, "# Title\n\n## Overview\n\n## Summary\n")
    result = run_guard(tmp_path, "check_doc_parity.py")
    assert result.returncode == 1
    assert "guide.md" in result.stderr
    assert "diverge" in result.stderr or "extra trailing" in result.stderr


def test_parity_blocks_a_one_sided_document(tmp_path):
    _parity_fixture(tmp_path, MATCHING_JA, MATCHING_EN)
    _parity_fixture(tmp_path, "# 片側だけ\n\n## 節\n", None, name="orphan.md")
    result = run_guard(tmp_path, "check_doc_parity.py")
    assert result.returncode == 1
    assert "no counterpart" in result.stderr


def test_parity_allows_a_recorded_gap(tmp_path):
    _parity_fixture(
        tmp_path,
        MATCHING_JA,
        "# Title\n\n## Overview\n\n## Summary\n",
        known="docs/ja/guide.md  # missing subsection, tracked\n",
    )
    result = run_guard(tmp_path, "check_doc_parity.py")
    assert result.returncode == 0, result.stderr
    assert "1 known gaps" in result.stdout


def test_parity_blocks_a_stale_recorded_gap(tmp_path):
    """An allowlist entry for a pair that now agrees is how a guard stops guarding."""
    _parity_fixture(
        tmp_path, MATCHING_JA, MATCHING_EN, known="docs/ja/guide.md  # long since fixed\n"
    )
    result = run_guard(tmp_path, "check_doc_parity.py")
    assert result.returncode == 1
    assert "no longer drift" in result.stderr


def test_parity_ignores_headings_inside_a_code_fence(tmp_path):
    """A '### ' in fenced output is example text, not structure."""
    ja = "# 題\n\n## 概要\n\n```\n### これは出力例\n```\n"
    en = "# Title\n\n## Overview\n\n```\n### this is sample output\n### and another\n```\n"
    _parity_fixture(tmp_path, ja, en)
    result = run_guard(tmp_path, "check_doc_parity.py")
    assert result.returncode == 0, result.stderr


def test_parity_blocks_when_it_finds_no_pairs_at_all(tmp_path):
    """Discovering nothing must fail, not report a clean tree."""
    (tmp_path / "docs").mkdir()
    result = run_guard(tmp_path, "check_doc_parity.py")
    assert result.returncode == 1
    assert "vacuous" in result.stderr


def test_parity_checks_the_suffix_convention_too(tmp_path):
    """Root README/TESTING and docs/agent/ pair as Y.md <-> Y_en.md."""
    _parity_fixture(tmp_path, MATCHING_JA, MATCHING_EN)
    (tmp_path / "README.md").write_text("# R\n\n## A\n\n### B\n", encoding="utf-8")
    (tmp_path / "README_en.md").write_text("# R\n\n## A\n", encoding="utf-8")
    result = run_guard(tmp_path, "check_doc_parity.py")
    assert result.returncode == 1
    assert "README.md" in result.stderr


def test_parity_checks_the_reversed_suffix_convention(tmp_path):
    """edge/soracom/ pairs as Y.md <-> Y_ja.md, with English as the primary file.

    Regression: the first version of this guard walked `*_en.md` only, so this
    pair was never compared and its absence did not show up anywhere in the
    output.
    """
    _parity_fixture(tmp_path, MATCHING_JA, MATCHING_EN)
    target = tmp_path / "edge" / "soracom"
    target.mkdir(parents=True)
    (target / "README.md").write_text("# S\n\n## A\n\n### B\n", encoding="utf-8")
    (target / "README_ja.md").write_text("# S\n\n## A\n", encoding="utf-8")
    result = run_guard(tmp_path, "check_doc_parity.py")
    assert result.returncode == 1
    assert "edge/soracom/README.md" in result.stderr


# ---------------------------------------------------------------------------
# check_sunset_services.py
# ---------------------------------------------------------------------------


def _sunset_fixture(root: Path, body: str, name: str = "docs/guide.md") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    # The guard needs at least one document to avoid its vacuous-run failure.
    (root / "README.md").write_text("# Reference\n\nNothing notable here.\n", encoding="utf-8")


def test_sunset_allows_a_document_naming_nothing_affected(tmp_path):
    _sunset_fixture(tmp_path, "# Guide\n\nUse Amazon Athena over an S3 access point.\n")
    result = run_guard(tmp_path, "check_sunset_services.py")
    assert result.returncode == 0, result.stderr
    assert "sunset services: OK" in result.stdout


def test_sunset_allows_a_mention_carrying_a_note(tmp_path):
    _sunset_fixture(
        tmp_path,
        "# Guide\n\nAmazon Timestream for LiveAnalytics has been closed to new "
        "customers since 2025-06-20; use Timestream for InfluxDB for new work.\n",
    )
    result = run_guard(tmp_path, "check_sunset_services.py")
    assert result.returncode == 0, result.stderr


def test_sunset_blocks_a_mention_with_no_note(tmp_path):
    _sunset_fixture(
        tmp_path, "# Guide\n\nSend the telemetry to Timestream for LiveAnalytics.\n"
    )
    result = run_guard(tmp_path, "check_sunset_services.py")
    assert result.returncode == 1
    assert "Timestream for LiveAnalytics" in result.stderr
    assert "docs/guide.md" in result.stderr


def test_sunset_still_blocks_when_the_word_maintenance_appears_unrelated(tmp_path):
    """Regression: bare "maintenance" as a marker made this guard vacuous.

    The English iot-greengrass-flexcache-integration.md names SageMaker Edge
    Manager with no note and passed the first version of this guard, because
    "predictive maintenance" appears elsewhere in it. Only one of two identical
    defects was reported.
    """
    _sunset_fixture(
        tmp_path,
        "# Guide\n\nA predictive maintenance pipeline. Package the model with "
        "SageMaker Edge Manager and deploy it to the fleet.\n",
    )
    result = run_guard(tmp_path, "check_sunset_services.py")
    assert result.returncode == 1
    assert "SageMaker Edge Manager" in result.stderr


def test_sunset_reports_the_source_so_the_status_is_auditable(tmp_path):
    _sunset_fixture(tmp_path, "# Guide\n\nUse AWS IoT Analytics for the channel.\n")
    result = run_guard(tmp_path, "check_sunset_services.py")
    assert result.returncode == 1
    assert "https://" in result.stderr


def test_sunset_does_not_match_a_service_name_inside_ordinary_prose(tmp_path):
    """Regression: an entry short enough to appear inside a phrase reports a false positive.

    "IoT Analytics" was in the inventory unqualified, and matched inside
    "Industrial IoT analytics" — a pattern name — so the catalog index was
    reported as a defect on the first run after the catalog was written.
    """
    _sunset_fixture(
        tmp_path,
        "# Guide\n\n| 03 | Industrial IoT analytics | Sensors to a data lake |\n",
    )
    result = run_guard(tmp_path, "check_sunset_services.py")
    assert result.returncode == 0, result.stderr


def test_sunset_blocks_when_it_finds_no_documents_at_all(tmp_path):
    result = run_guard(tmp_path, "check_sunset_services.py")
    assert result.returncode == 1
    assert "vacuous" in result.stderr


# ---------------------------------------------------------------------------
# check_diagram_assets.py
# ---------------------------------------------------------------------------

FIGURES = ("architecture-overview", "pattern-01-edge-ai-bedrock", "pattern-05-agentic-rag")

_DRAWIO = '<mxfile><diagram name="x"><root><mxCell id="0"/></root></diagram></mxfile>'


def _diagram_fixture(root: Path) -> None:
    """A tree with all 18 artifacts present and no Japanese in the English ones."""
    diagrams = root / "docs" / "diagrams"
    images = root / "docs" / "images"
    png = images / "png"
    for directory in (diagrams, png):
        directory.mkdir(parents=True, exist_ok=True)
    for figure in FIGURES:
        for stem in (figure, f"{figure}-en"):
            (diagrams / f"{stem}.drawio").write_text(_DRAWIO, encoding="utf-8")
            (images / f"{stem}.svg").write_text("<svg>Edge site</svg>", encoding="utf-8")
        (png / f"{figure}@2x.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (png / f"{figure}-en@2x.png").write_bytes(b"\x89PNG\r\n\x1a\n")


def test_diagram_assets_allow_a_complete_set(tmp_path):
    _diagram_fixture(tmp_path)
    result = run_guard(tmp_path, "check_diagram_assets.py")
    assert result.returncode == 0, result.stderr
    assert "18 artifacts" in result.stdout


def test_diagram_assets_block_a_committed_icon_library_file(tmp_path):
    _diagram_fixture(tmp_path)
    (tmp_path / "docs" / "Arch_Amazon-Athena_64.svg").write_text("<svg/>", encoding="utf-8")
    result = run_guard(tmp_path, "check_diagram_assets.py")
    assert result.returncode == 1
    assert "Arch_Amazon-Athena_64.svg" in result.stderr
    assert "redistribution" in result.stderr


def test_diagram_assets_block_a_figure_never_re_exported(tmp_path):
    """The failure this guard exists for: the .drawio changed, the SVG did not follow."""
    _diagram_fixture(tmp_path)
    (tmp_path / "docs" / "images" / "pattern-05-agentic-rag.svg").unlink()
    result = run_guard(tmp_path, "check_diagram_assets.py")
    assert result.returncode == 1
    assert "pattern-05-agentic-rag.svg: missing" in result.stderr


def test_diagram_assets_block_an_empty_export(tmp_path):
    _diagram_fixture(tmp_path)
    (tmp_path / "docs" / "images" / "png" / "architecture-overview@2x.png").write_bytes(b"")
    result = run_guard(tmp_path, "check_diagram_assets.py")
    assert result.returncode == 1
    assert "empty" in result.stderr


def test_diagram_assets_block_japanese_left_in_an_english_artifact(tmp_path):
    _diagram_fixture(tmp_path)
    (tmp_path / "docs" / "images" / "architecture-overview-en.svg").write_text(
        "<svg>エッジ拠点</svg>", encoding="utf-8"
    )
    result = run_guard(tmp_path, "check_diagram_assets.py")
    assert result.returncode == 1
    assert "architecture-overview-en.svg" in result.stderr


def test_diagram_assets_block_a_reference_marker_left_untranslated(tmp_path):
    """U+203B sits outside every CJK block, so a range check written the obvious way
    reports this file as clean.
    """
    _diagram_fixture(tmp_path)
    (tmp_path / "docs" / "diagrams" / "pattern-01-edge-ai-bedrock-en.drawio").write_text(
        _DRAWIO.replace('name="x"', 'name="S3 access point ※1"'), encoding="utf-8"
    )
    result = run_guard(tmp_path, "check_diagram_assets.py")
    assert result.returncode == 1
    assert "※" in result.stderr


def test_diagram_assets_block_unparseable_drawio(tmp_path):
    _diagram_fixture(tmp_path)
    (tmp_path / "docs" / "diagrams" / "architecture-overview.drawio").write_text(
        '<mxfile><diagram name="x">', encoding="utf-8"
    )
    result = run_guard(tmp_path, "check_diagram_assets.py")
    assert result.returncode == 1
    assert "not well-formed" in result.stderr


def test_diagram_assets_block_an_empty_tree_rather_than_passing_vacuously(tmp_path):
    result = run_guard(tmp_path, "check_diagram_assets.py")
    assert result.returncode == 1
    assert "missing" in result.stderr
