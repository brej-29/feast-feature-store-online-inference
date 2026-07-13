"""
Feast feature repository package for the fraud detection project.

Contains:
- Entity definitions
- Data sources
- Feature views
- Feature services

The Feast CLI executes these files with the repo directory on sys.path, so
the modules use bare imports (``from data_sources import ...``). Add the repo
directory to sys.path here as well so package-style imports
(``feature_repo.feature_views``) also work, e.g. from tests.
"""

import os
import sys

_REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if _REPO_DIR not in sys.path:
    sys.path.append(_REPO_DIR)
