"""The pin gate must block the shapes that let a fabricated SHA through.

The defect it was written for: `github/codeql-action/upload-sarif` was pinned to a
40-character SHA that is not a commit in that repository, commented `# v3.28.0`.
The pin was well-formed, so shape checks passed; the workflow failed at action
resolution on every push to main, and the README badge pointed at a scan that had
never run.

The offline half is tested against synthetic workflow trees. The networked half
(`--verify`) is exercised without a network by substituting the module's `api`
function, so the test does not depend on GitHub answering or on a rate limit.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "check_action_pins.py"


def load_gate(root: Path):
    """Import the real script with its REPO_ROOT pointing at a fixture tree."""
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    copied = scripts / GATE.name
    shutil.copy2(GATE, copied)
    spec = importlib.util.spec_from_file_location(f"pins_{root.name}", copied)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_gate(root: Path) -> subprocess.CompletedProcess[str]:
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GATE, scripts / GATE.name)
    return subprocess.run(
        [sys.executable, str(scripts / GATE.name)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def workflow(root: Path, name: str, uses: str) -> None:
    path = root / ".github" / "workflows" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "name: w\non:\n  push:\njobs:\n  j:\n    runs-on: ubuntu-latest\n"
        f"    steps:\n      - uses: {uses}\n",
        encoding="utf-8",
    )


SHA_A = "a" * 40
SHA_B = "b" * 40


def test_allows_a_sha_pin_with_a_version_comment(tmp_path):
    workflow(tmp_path, "w.yml", f"actions/checkout@{SHA_A} # v4.2.2")
    result = run_gate(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "1 pin(s) well-formed" in result.stdout


def test_blocks_a_tag_pin(tmp_path):
    workflow(tmp_path, "w.yml", "actions/checkout@v4")
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert "pinned to a mutable ref" in result.stderr


def test_blocks_a_sha_with_no_version_comment(tmp_path):
    workflow(tmp_path, "w.yml", f"actions/checkout@{SHA_A}")
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert "no version comment" in result.stderr


def test_allows_a_local_action(tmp_path):
    workflow(tmp_path, "w.yml", "./.github/actions/thing")
    assert run_gate(tmp_path).returncode == 0


def test_verify_blocks_a_sha_that_does_not_exist(tmp_path):
    """The measured defect. Shape is fine; the commit is not there."""
    workflow(tmp_path, "w.yml", f"github/codeql-action/upload-sarif@{SHA_A} # v3.28.0")
    module = load_gate(tmp_path)
    module.api = lambda path, auth: None  # every lookup misses
    assert module.check(verify=True) == 1


def test_verify_blocks_a_comment_naming_another_version(tmp_path):
    """The second defect this found: the pin was v2.3.9, the comment said v2.3.8."""
    workflow(tmp_path, "w.yml", f"gitleaks/gitleaks-action@{SHA_A} # v2.3.8")

    def api(path, auth):
        return {"sha": SHA_A} if path.endswith(SHA_A) else {"sha": SHA_B}

    module = load_gate(tmp_path)
    module.api = api
    assert module.check(verify=True) == 1


def test_verify_allows_a_pin_matching_its_comment(tmp_path):
    workflow(tmp_path, "w.yml", f"actions/checkout@{SHA_A} # v4.2.2")
    module = load_gate(tmp_path)
    module.api = lambda path, auth: {"sha": SHA_A}
    assert module.check(verify=True) == 0


def test_verify_does_not_fail_on_a_rate_limit(tmp_path):
    """"GitHub would not answer" is not "the pin is wrong". It is reported and the
    run continues, so a rate limit cannot be mistaken for a verdict."""
    workflow(tmp_path, "w.yml", f"actions/checkout@{SHA_A} # v4.2.2")
    module = load_gate(tmp_path)

    def api(path, auth):
        raise module.RateLimited("HTTP 403")

    module.api = api
    assert module.check(verify=True) == 0


def test_the_makefile_still_invokes_the_gate():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "scripts/check_action_pins.py" in makefile
    lint_line = next(line for line in makefile.splitlines() if line.startswith("lint:"))
    assert "action-pins" in lint_line.split("##")[0].split(), lint_line


def test_this_repository_passes_the_offline_half():
    result = subprocess.run(
        [sys.executable, str(GATE)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
