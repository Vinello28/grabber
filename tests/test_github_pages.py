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


def test_css_responsive_design_and_breakpoints():
    """Verify that styles.css defines robust responsive breakpoints, fluid grids, and touch scroll."""
    css = STYLES_CSS.read_text(encoding="utf-8")

    # Responsive Breakpoints
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 768px)" in css
    assert "@media (max-width: 480px)" in css
    assert "@media (max-width: 360px)" in css

    # Fluid grids that never overflow 320px/360px viewports
    assert "minmax(min(100%, 300px), 1fr)" in css
    assert "minmax(min(100%, 280px), 1fr)" in css
    assert "minmax(min(100%, 220px), 1fr)" in css

    # Benchmark table touch scroll and min-width
    assert "-webkit-overflow-scrolling: touch" in css
    assert "min-width: 620px" in css

    # Terminal tabs touch scroll
    assert "overflow-x: auto" in css
    assert "scrollbar-width: none" in css

    # Nav toggle active state
    assert ".nav-toggle-btn.is-active" in css


def test_mobile_navigation_accessibility_and_ux():
    """Verify accessible markup and click-outside dismissal in script.js and index.html."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = SCRIPT_JS.read_text(encoding="utf-8")

    # Accessibility attributes on toggle button
    assert 'aria-expanded="false"' in html
    assert "icon-hamburger" in html
    assert "icon-close" in html

    # JS click-outside and aria-expanded toggle
    assert "closeMobileMenu" in js
    assert "aria-expanded" in js
    assert "mobile-open" in js


def test_readme_english_and_for_the_badge_shields():
    """Verify that README.md is in English and features 'for-the-badge' tech stack shields."""
    readme_path = DOCS_DIR.parent / "README.md"
    assert readme_path.is_file(), "README.md must exist in repo root"
    content = readme_path.read_text(encoding="utf-8")

    # Tech stack shields with style=for-the-badge
    for tech in ["Python", "DuckDB", "Streamlit", "Apache%20Arrow", "Pandas", "Pytest", "Ruff", "GitHub%20Actions"]:
        assert tech in content, f"Tech shield for '{tech}' missing in README.md"
    assert "style=for-the-badge" in content

    # English headings
    assert "## Architecture and Design Principles" in content
    assert "## 🚀 Key Features" in content
    assert "## 💻 Installation & Quickstart" in content
    assert "## 📦 Standalone Executables (Double-Click with Icon) & GitHub Releases" in content
    assert "## 🧪 Benchmarks on Test Datasets" in content
    assert "## 📂 Project Structure" in content
    assert "## 📜 Copyright and License" in content

    # English legal terms
    assert "Anti-Commercial Analytics Prohibition" in content
    assert "Personal and Academic Use" in content

