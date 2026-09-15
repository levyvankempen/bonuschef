"""What version is this.

The question "is the fix live?" used to require reading source inside a
container and comparing it by eye, because nothing the deployment ran
carried its own provenance.
"""

from __future__ import annotations

import os
from importlib import metadata

UNKNOWN = "unknown"


def get_version() -> str:
    """The version this process is running.

    Resolution order, widest evidence first:

    1. ``BONUSCHEF_VERSION`` from the environment. The image sets it at build
       time from ``git describe``, so it is the only source that can say a
       build came from a modified tree rather than the release it resembles.
    2. The installed package's metadata, for running outside Docker where the
       build argument was never set.
    3. ``"unknown"``.

    Never raises. This renders in the portal chrome, and a version banner
    that can take the page down with it is worse than no banner.
    """
    stamped = os.environ.get("BONUSCHEF_VERSION", "").strip()
    if stamped and stamped != UNKNOWN:
        return stamped

    try:
        return metadata.version("bonuschef")
    except Exception:
        return UNKNOWN


def is_stamped() -> bool:
    """Whether the version came from the build rather than from a guess.

    An unstamped process fell back to package metadata, which reports the
    number semantic-release last wrote to pyproject.toml. That number cannot
    tell a clean tag from a working tree sitting three commits past it, so it
    is not evidence of anything about provenance.
    """
    stamped = os.environ.get("BONUSCHEF_VERSION", "").strip()
    return bool(stamped) and stamped != UNKNOWN


def get_commit() -> str:
    """The commit this process was built from, or ``"unknown"``."""
    return os.environ.get("BONUSCHEF_COMMIT", "").strip() or UNKNOWN


def is_release() -> bool:
    """Whether this is a released version rather than a build in between.

    ``git describe`` appends a commit count past the tag, and ``-dirty`` for
    uncommitted changes. Either means what is running does not correspond to
    anything that was ever tagged and tested.
    """
    if not is_stamped():
        # Unstamped: running from a source checkout, or an image built before
        # stamping existed. Claiming "release" here would be the exact
        # confusion this module exists to prevent, so answer no.
        return False
    version = get_version()
    if version == UNKNOWN or version.endswith(("-dirty", "-nogit")):
        return False
    # v1.3.0 is a release; v1.3.0-5-gabc1234 is five commits past one.
    return "-" not in version.removeprefix("v")


def describe() -> str:
    """A short human-readable stamp for the portal chrome."""
    version = get_version()
    if version == UNKNOWN:
        return "versie onbekend"
    return version if is_release() else f"{version} (geen release)"
