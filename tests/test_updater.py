"""
Unit tests for GitHub Releases updater and semantic version comparison.
"""

from src.core.updater import GitHubUpdater, ReleaseInfo
from src.core.version import __version__


def test_release_info_semver_comparison():
    # Newer release
    newer = ReleaseInfo(
        tag_name="v2.0.0",
        version_str="2.0.0",
        name="Version 2.0.0",
        release_notes="Major update",
        html_url="https://github.com/test/repo/releases/v2.0.0",
        published_at="2026-10-01",
    )
    assert newer.is_newer_than_current is True

    # Same version
    current = ReleaseInfo(
        tag_name=f"v{__version__}",
        version_str=__version__,
        name=f"Version {__version__}",
        release_notes="Current version",
        html_url="https://github.com/test/repo/releases",
        published_at="2026-10-01",
    )
    assert current.is_newer_than_current is False

    # Older version
    older = ReleaseInfo(
        tag_name="v0.5.0",
        version_str="0.5.0",
        name="Old version",
        release_notes="Old",
        html_url="https://github.com/test/repo/releases",
        published_at="2025-01-01",
    )
    assert older.is_newer_than_current is False


def test_platform_asset_matching():
    updater = GitHubUpdater(repo="test/repo")
    mock_assets = [
        {"name": "Grabber-Windows.zip", "browser_download_url": "https://download/win.zip", "size": 50000},
        {"name": "Grabber-macOS.zip", "browser_download_url": "https://download/mac.zip", "size": 60000},
        {"name": "Grabber-Linux.tar.gz", "browser_download_url": "https://download/linux.tar.gz", "size": 55000},
    ]

    matched = updater._find_platform_asset(mock_assets)
    assert matched is not None
    assert "download_url" in matched
    assert "name" in matched


def test_offline_or_nonexistent_repo_graceful_handling():
    # Invalid repository should return None gracefully without raising
    updater = GitHubUpdater(repo="nonexistent_user_xyz/nonexistent_repo_abc_123")
    res = updater.check_for_updates(timeout_sec=1.0)
    assert res is None


def test_ssl_context_trusts_certifi_bundle_independent_of_openssl_paths():
    """Frozen builds ship an OpenSSL whose default CA path does not exist on user machines."""
    from unittest.mock import patch

    from src.core.updater import _ssl_context

    with patch("ssl.create_default_context") as create:
        _ssl_context()
    assert create.call_args.kwargs["cafile"].endswith("cacert.pem")
