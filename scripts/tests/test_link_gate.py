"""The link gate must block the defects it exists for.

A gate that has only ever passed is indistinguishable from a gate that cannot
fail. `scripts/check_links.py` reported 990 resolved links on its first run
against this repository, which is exactly the result a no-op would print. Each
case below builds a synthetic repository, copies the real script into
`<fixture>/scripts/` (the script resolves its root from `parents[1]`, so it then
treats the fixture as the repository), and asserts the verdict.

The offline mode is what is tested. Probing URLs is left out on purpose: a test
that needs github.com to answer fails for reasons that have nothing to do with
this repository.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "scripts" / "check_links.py"


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


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_allows_links_that_resolve(tmp_path):
    write(tmp_path, "docs/ja/target.md", "# T\n\n## 姉妹リポジトリの数値を引くときの条件\n")
    write(
        tmp_path,
        "README.md",
        "# R\n\n## 見出し\n\n"
        "[doc](docs/ja/target.md)\n"
        "[anchor](docs/ja/target.md#姉妹リポジトリの数値を引くときの条件)\n"
        "[same doc](#見出し)\n"
        "[external](https://example.invalid/page)\n"
        "[mail](mailto:someone@example.com)\n",
    )
    result = run_gate(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "links: OK" in result.stdout


def test_blocks_a_missing_file(tmp_path):
    write(tmp_path, "README.md", "# R\n\n[gone](docs/ja/absent.md)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert "file not found: docs/ja/absent.md" in result.stderr


def test_blocks_an_anchor_that_no_longer_exists(tmp_path):
    """The defect this gate is mostly for: GitHub answers an unknown fragment
    with the top of the page, so a renamed heading breaks nothing visibly."""
    write(tmp_path, "docs/en/target.md", "# T\n\n## Conditions for citing numbers\n")
    write(tmp_path, "README.md", "# R\n\n[cited](docs/en/target.md#conditions-for-citing)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert "anchor '#conditions-for-citing' not found in docs/en/target.md" in result.stderr


def test_blocks_a_broken_same_document_anchor(tmp_path):
    write(tmp_path, "README.md", "# R\n\n## Real heading\n\n[jump](#renamed-heading)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert "anchor '#renamed-heading' not found in this document" in result.stderr


def test_blocks_a_link_out_of_the_repository(tmp_path):
    write(tmp_path, "docs/ja/note.md", "# N\n\n[up](../../../etc/hosts)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert "escapes the repository root" in result.stderr


def test_blocks_a_directory_that_would_not_survive_a_clone(tmp_path):
    (tmp_path / "docs" / "images" / "png").mkdir(parents=True)
    write(tmp_path, "README.md", "# R\n\n[figures](docs/images/png)\n")
    result = run_gate(tmp_path)
    assert result.returncode == 1
    assert "will not survive a clone" in result.stderr


def test_allows_a_directory_holding_a_tracked_file(tmp_path):
    write(tmp_path, "docs/images/png/figure.svg", "<svg/>\n")
    write(tmp_path, "README.md", "# R\n\n[figures](docs/images/png)\n")
    assert run_gate(tmp_path).returncode == 0


def test_ignores_links_inside_a_fenced_block(tmp_path):
    """Documenting a blind spot rather than asserting it is desirable: the clone
    URL that pointed at the pre-rename repository name lived in a bash fence, so
    this gate would not have caught it."""
    write(tmp_path, "SETUP.md", "# S\n\n```bash\n[absent](docs/gone.md)\n```\n")
    assert run_gate(tmp_path).returncode == 0


def test_ignores_image_embeds_but_not_file_links(tmp_path):
    write(tmp_path, "README.md", "# R\n\n![alt](docs/images/absent.svg)\n")
    assert run_gate(tmp_path).returncode == 0
    write(tmp_path, "README.md", "# R\n\n[svg](docs/images/absent.svg)\n")
    assert run_gate(tmp_path).returncode == 1


def test_skips_working_material_that_is_not_published(tmp_path):
    write(tmp_path, ".private/draft.md", "# D\n\n[gone](nowhere.md)\n")
    write(tmp_path, ".kiro/specs/notes.md", "# N\n\n[gone](nowhere.md)\n")
    assert run_gate(tmp_path).returncode == 0


def test_refuses_a_non_http_scheme_without_opening_it():
    """`urlopen` accepts `file:` and custom schemes. A Markdown link is reachable
    by anyone who can open a pull request, so the probe refuses anything else
    before the request is built rather than relying on its caller."""
    spec = importlib.util.spec_from_file_location("check_links", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verdict = module.check_external("file:///etc/hosts")
    assert verdict is not None
    assert "refusing to probe" in verdict


def test_the_makefile_still_invokes_the_gate():
    """An orphaned gate is a gate that runs nowhere. `make lint` must call it."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "scripts/check_links.py" in makefile
    assert "links:" in makefile
    lint_line = next(
        line for line in makefile.splitlines() if line.startswith("lint:")
    )
    assert "links" in lint_line.split("##")[0].split(), lint_line
