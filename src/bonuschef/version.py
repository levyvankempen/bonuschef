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


# Production is the unnamed case.
#
# An invited person has one environment, and labelling it would be noise on
# every page they ever see. So the absence of a value means production, and any
# value other than "production" means somewhere that must say so.
PRODUCTION = "production"


def get_environment() -> str:
    """Which environment this process is, lowercased.

    ``"production"`` when nothing says otherwise - including when the variable
    is set to an empty string, which is what an env file with a bare
    ``BONUSCHEF_ENVIRONMENT=`` produces.
    """
    named = os.environ.get("BONUSCHEF_ENVIRONMENT", "").strip().lower()
    return named or PRODUCTION


def is_production() -> bool:
    """Whether this is the deployment the invited people use.

    Defaults to True on purpose. A misconfigured environment that believes it
    is production shows no banner, which is the quiet failure; one that
    believes it is a test environment shows a banner on production, which the
    invited people would see and ask about. Neither is good, and the first is
    recoverable by reading a config file while the second is a page everybody
    is looking at.

    The reason it is still the default: every other value here comes from a
    deployment that deliberately set one, and production is the deployment
    that sets nothing.
    """
    return get_environment() == PRODUCTION


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
