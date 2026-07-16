"""Expose Ubuntu's GI bindings after virtual-environment packages are loaded."""

import sys
from pathlib import Path

UBUNTU_PACKAGES = Path("/usr/lib/python3/dist-packages")
if UBUNTU_PACKAGES.is_dir() and str(UBUNTU_PACKAGES) not in sys.path:
    sys.path.append(str(UBUNTU_PACKAGES))
