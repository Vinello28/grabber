"""
Application version and repository definition.
"""

import os

__version__ = "1.0.0"

# Target GitHub repository for update checks (owner/repo)
# Can be overridden via environment variable GRABBER_GITHUB_REPO
GITHUB_REPO = os.getenv("GRABBER_GITHUB_REPO", "gabrielevianello/grabber")
