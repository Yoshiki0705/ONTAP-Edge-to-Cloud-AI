"""The ai-style gate must still fire, and must stay wired into CI.

`scripts/ai_style_rules.py` is a byte-for-byte copy of the Hub detector. A copy
can silently stop running two ways: the detector's own `--selftest` could pass
while the Makefile target or the CI step quietly drops it. This file asserts all
three — the detector flags both directions, `make ai-style:` is defined, and
test.yml's lint job invokes `make ai-style` — so the report-only gate cannot
become a no-op without a red test.

The detector is standalone stdlib (it imports nothing from the repository and
does no sys.path insert), so it is copied into a synthetic tree and run there,
following scripts/tests/test_link_gate.py.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "ai_style_rules.py"

# The D1 positive from the detector's own examples: the Japanese bracketed-bold
# form whose '**' does not render as bold. A fail-level rule, so --fail exits 1.
D1_POSITIVE = "上は**「自分の構成」**で引く。\n"
# The matching negative from the same rule: the marker moved outside the brackets.
D1_NEGATIVE = "次は**自分の構成**で引く。\n"


def run_gate(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    scripts = cwd / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GATE, scripts / GATE.name)
    return subprocess.run(
        [sys.executable, str(scripts / GATE.name), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_selftest_passes_and_names_the_rule_count(tmp_path):
    """A detector that has never been seen to fail is not evidence it can fail.
    --selftest asserts every rule fires on its positive and not its negative."""
    result = run_gate(["--selftest"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "20 rule(s) fire on their positives and not their negatives" in result.stdout


def test_clean_prose_exits_zero_even_with_fail(tmp_path):
    write(tmp_path, "docs/ja/clean.md", "# 見出し\n\n" + D1_NEGATIVE)
    result = run_gate(["docs", "--fail"], tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_planted_d1_fails_with_fail_flag(tmp_path):
    write(tmp_path, "docs/ja/dirty.md", "# 見出し\n\n" + D1_POSITIVE)
    result = run_gate(["docs", "--fail"], tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "D1" in result.stdout


def test_report_only_scan_lists_a_planted_d1_without_the_fail_flag(tmp_path):
    """Without --fail the gate still only reports: a D1 is listed, exit stays 0.
    This isolates the gating to the flag, so the flip is what makes a D1 break."""
    write(tmp_path, "docs/ja/dirty.md", "# 見出し\n\n" + D1_POSITIVE)
    result = run_gate(["docs", "--summary"], tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def _ai_style_recipe(makefile: str) -> str:
    """The lines of the `ai-style:` recipe (the target line plus its tab-indented
    body), so an assertion about the recipe cannot be satisfied by --fail sitting
    on some unrelated target."""
    lines = makefile.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("ai-style:"))
    body = [lines[start]]
    for line in lines[start + 1 :]:
        if line.startswith("\t") or not line.strip():
            body.append(line)
            if line.strip():
                continue
        else:
            break
    return "\n".join(body)


def test_the_makefile_defines_the_target_and_gates_with_fail():
    """An orphaned gate runs nowhere, and a gate without --fail never blocks. The
    target must exist, call the real script, and the scan line must carry --fail."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "ai-style:" in makefile
    assert "scripts/ai_style_rules.py" in makefile
    recipe = _ai_style_recipe(makefile)
    assert "scripts/ai_style_rules.py" in recipe
    # The flip: the scan command (not --selftest) now gates with --fail.
    scan_line = next(
        line
        for line in recipe.splitlines()
        if "ai_style_rules.py" in line and "--selftest" not in line
    )
    assert "--fail" in scan_line, scan_line
    phony = next(
        (line for line in makefile.splitlines() if "ai-style" in line and ".PHONY" in line),
        None,
    )
    # ai-style spans the .PHONY continuation; assert it is declared phony so a
    # directory named ai-style could never shadow the recipe.
    assert "ai-style" in makefile.split(".PHONY:", 1)[1].split("\n\n", 1)[0], phony


def test_ci_lint_job_invokes_the_gate_and_documents_fail():
    """CI runs neither `make check` nor `make lint`, so the gate has to be its own
    named step in test.yml's lint job or it never runs in CI. The step invokes
    `make ai-style`, which carries --fail, and the step records that it gates so the
    flip is visible where CI is read."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    assert "make ai-style" in workflow
    # The ai-style step block must mention --fail, so the gating is not invisible to
    # a reader of the workflow (the Makefile is the source of truth for the flag).
    step = workflow.split("ai-style gate", 1)[1].split("- name:", 1)[0]
    assert "--fail" in step, step
