"""Tests for README.md and docs/architecture.md: link validity and no em dashes."""

import os
import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("rel_path", ["README.md", "docs/architecture.md"])
def test_document_has_no_em_dashes(rel_path: str) -> None:
    doc_path = REPO_ROOT / rel_path
    assert doc_path.exists(), f"File missing: {rel_path}"
    content = doc_path.read_text(encoding="utf-8")
    assert "\u2014" not in content, f"Em dash (\\u2014) detected in {rel_path}"


@pytest.mark.parametrize("rel_path", ["README.md", "docs/architecture.md"])
def test_document_relative_links_resolve(rel_path: str) -> None:
    doc_path = REPO_ROOT / rel_path
    assert doc_path.exists(), f"File missing: {rel_path}"
    content = doc_path.read_text(encoding="utf-8")
    doc_dir = doc_path.parent

    # Match standard markdown links and images: [text](target)
    md_links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", content)
    # Match html img tags: <img ... src="target" ...>
    html_imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content)

    all_targets = md_links + html_imgs
    unresolved: list[str] = []

    for target in all_targets:
        # Strip query parameters or anchor fragments
        clean_target = target.split("?")[0].split("#")[0].strip()
        if not clean_target:
            continue
        # Allow external web URLs, anchors, mailto, and intentional placeholders
        if clean_target.startswith(("http://", "https://", "mailto:", "#")) or clean_target == "VIDEO_URL":
            continue

        resolved_from_doc = (doc_dir / clean_target).resolve()
        resolved_from_root = (REPO_ROOT / clean_target).resolve()

        if not (resolved_from_doc.exists() or resolved_from_root.exists()):
            unresolved.append(f"{target} (referenced in {rel_path})")

    assert not unresolved, f"Unresolved relative links found:\n" + "\n".join(unresolved)


def test_mermaid_sequence_messages_have_no_semicolons() -> None:
    """GitHub's Mermaid treats ';' as a statement break inside a sequence message and refuses to render the diagram."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for name in ("README.md", "docs/architecture.md"):
        for block in re.findall(r"```mermaid\n(.*?)```", (root / name).read_text(encoding="utf-8"), re.S):
            if "sequenceDiagram" in block:
                for line in block.splitlines():
                    if ":" in line:
                        assert ";" not in line.split(":", 1)[1], f"{name}: {line.strip()}"
