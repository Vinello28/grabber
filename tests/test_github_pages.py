"""
Unit tests for Grabber GitHub Pages showcase and documentation site.
Verifies HTML markup integrity, internal links, CSS theming, and script bindings.
Copyright (c) 2026 Gabriele Vianello.
"""

import re
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
INDEX_HTML = DOCS_DIR / "index.html"
STYLES_CSS = DOCS_DIR / "styles.css"
SCRIPT_JS = DOCS_DIR / "script.js"


def test_docs_files_exist():
    """Verify that all core website files are present."""
    assert INDEX_HTML.is_file(), "index.html must exist in docs/"
    assert STYLES_CSS.is_file(), "styles.css must exist in docs/"
    assert SCRIPT_JS.is_file(), "script.js must exist in docs/"
    assert (DOCS_DIR / "assets" / "icon.png").is_file(), "icon.png must exist in docs/assets/"
    assert (DOCS_DIR / "assets" / "favicon.ico").is_file(), "favicon.ico must exist in docs/assets/"
    assert (DOCS_DIR / ".nojekyll").is_file(), ".nojekyll must exist in docs/"


def test_html_structure_and_meta():
    """Verify semantic HTML5 tags and essential SEO meta headers."""
    content = INDEX_HTML.read_text(encoding="utf-8")

    assert "<!DOCTYPE html>" in content
    assert '<html lang="en"' in content
    assert "<title>Grabber — Big Data Analytical Engine & GUI</title>" in content
    assert '<meta name="viewport"' in content
    assert '<meta name="description"' in content
    assert 'href="styles.css"' in content
    assert 'src="script.js"' in content
    assert "data-theme=" in content


def test_internal_anchor_links_match_ids():
    """Verify that all hash navigation links (#...) match actual element IDs in the document."""
    content = INDEX_HTML.read_text(encoding="utf-8")

    # Find all href="#xyz"
    href_anchors = set(re.findall(r'href="#([a-zA-Z0-9_-]+)"', content))
    # Exclude empty or dummy anchors
    href_anchors.discard("")

    # Find all id="xyz"
    element_ids = set(re.findall(r'id="([a-zA-Z0-9_-]+)"', content))

    for anchor in href_anchors:
        assert anchor in element_ids, f"Anchor #{anchor} referenced in href does not match any element ID in index.html"


def test_css_theming_and_accents():
    """Verify that styles.css defines dark/light tokens, yellow and green accents."""
    css = STYLES_CSS.read_text(encoding="utf-8")

    # Root and Light theme
    assert ":root" in css
    assert '[data-theme="light"]' in css

    # Accents: Yellow/Gold and Green/Emerald
    assert "--accent-yellow:" in css
    assert "--accent-green:" in css
    assert "--bg-primary:" in css
    assert "--text-primary:" in css


def test_js_element_bindings():
    """Verify that all DOM element IDs manipulated in script.js exist in index.html."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    expected_ids = [
        "theme-toggle-btn",
        "nav-toggle-btn",
        "nav-links",
        "sim-grabber-ram",
        "sim-grabber-time",
        "sim-grabber-bar",
        "sim-trad-ram",
        "sim-trad-status",
        "sim-trad-bar",
    ]

    for elem_id in expected_ids:
        assert f'id="{elem_id}"' in html, f"Expected ID '{elem_id}' referenced in script.js was not found in index.html"


def test_github_actions_workflow():
    """Verify that .github/workflows/deploy-pages.yml is valid and configured."""
    workflow = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "deploy-pages.yml"
    assert workflow.is_file(), "deploy-pages.yml must exist"
    content = workflow.read_text(encoding="utf-8")
    assert "actions/deploy-pages" in content
    assert "upload-pages-artifact" in content
    assert "path: 'docs'" in content
