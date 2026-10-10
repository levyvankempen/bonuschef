"""What had to change before a second environment could exist at all.

None of this is the test environment. It is the three things that made a second
stack on this host impossible, each of which was an accident rather than a
decision:

- every service set `container_name`, and Compose's project prefix does not
  apply to an explicit name, so a second stack collides on all four;
- every published port was a literal, so a second stack collides on those too;
- the project name came from the directory basename, which is `bonuschef` on
  the host because somebody cloned into /opt/bonuschef - and the volume names
  follow it.

The last one was verified against the running deployment before being written
down: `com.docker.compose.project=bonuschef`, volumes `bonuschef_pg_data` and
`bonuschef_dagster_home`. Pinning the same name renames nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

# The names the four services used to be pinned to. Nothing in a live file may
# address a container by one of these again: with the names derived from the
# project, `pg_bonuschef` either does not exist or belongs to whichever stack
# claimed it.
RETIRED_NAMES = (
    "pg_bonuschef",
    "dagster_webserver",
    "dagster_daemon",
    "streamlit_portal",
)

# Where an operational instruction can actually live: something that is run, or
# that a human follows while fixing production.
#
# Two directories are deliberately out of scope. OpenSpec, because a proposal
# describing what the old names were, or an archived change recording what was
# true when it was written, is prose about the past - rewriting it to match
# today would falsify the history that makes it worth keeping. And tests,
# because they are where the names are written down in order to be forbidden:
# test_copy_to_test.py asserts the copy script does not guess a container name,
# which it can only do by naming the ones it must not use.
LIVE = ("scripts", "docs", "deploy", "src")
LIVE_SUFFIXES = {".sh", ".md", ".py", ".yml", ".yaml", ".service", ".timer"}


def _live_files() -> list[Path]:
    """Scanned once. Four parametrised cases over the whole tree took 68s."""
    found = [
        path
        for top in LIVE
        for path in (REPO_ROOT / top).rglob("*")
        if path.is_file() and path.suffix in LIVE_SUFFIXES
    ]
    found += [
        path
        for path in REPO_ROOT.glob("*")
        if path.is_file() and path.suffix in LIVE_SUFFIXES
    ]
    return [p for p in found if ".venv" not in p.parts]


LIVE_FILES = _live_files()


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())


class TestNothingPinsAContainerName:
    def test_no_service_sets_container_name(self, compose):
        pinned = [
            name
            for name, svc in compose["services"].items()
            if svc.get("container_name")
        ]
        assert not pinned, (
            f"{pinned} pin a container name. A second stack on this host "
            "collides immediately - Compose's project prefix does not apply to "
            "an explicit container_name."
        )

    @pytest.mark.parametrize("retired", RETIRED_NAMES)
    def test_no_live_file_addresses_a_container_by_its_old_name(self, retired: str):
        """The names are gone, so a command naming one is now either addressing
        nothing or addressing a container belonging to the other environment.

        Both failures are quiet: `docker exec pg_bonuschef psql` prints an error
        into a shell nobody is reading, and the documented recovery step it was
        part of silently does not happen.
        """
        offenders = [
            path.relative_to(REPO_ROOT).as_posix()
            for path in LIVE_FILES
            if retired in path.read_text(encoding="utf-8", errors="ignore")
        ]
        assert not offenders, (
            f"{retired} is still addressed in {offenders}. Use the service name "
            "through `docker compose exec`, which resolves within one project."
        )


class TestNoPortIsALiteral:
    def test_every_published_port_is_overridable(self, compose):
        published = [
            (name, str(mapping))
            for name, svc in compose["services"].items()
            for mapping in svc.get("ports", [])
        ]
        assert published, "expected at least one published port"
        for name, mapping in published:
            assert "${" in mapping, (
                f"{name} publishes {mapping} as a literal, so a second stack "
                "cannot move it without a second copy of the file"
            )

    def test_the_defaults_are_todays_ports(self, compose):
        """Production must be unchanged by this. A deployment that comes back
        on a different port is one nobody can reach, and the Tailscale serve
        configuration in front of it names 8501.
        """
        expected = {
            "postgres": "5455",
            "dagster-webserver": "3000",
            "streamlit": "8501",
        }
        for service, port in expected.items():
            mapping = str(compose["services"][service]["ports"][0])
            default = re.search(r":-(\d+)\}", mapping)
            assert default, f"{service} has no default port: {mapping}"
            assert default.group(1) == port, (
                f"{service} would come back on {default.group(1)}, not {port}"
            )

    def test_every_published_port_still_binds_to_loopback(self, compose):
        """The variable must not have swallowed the interface. `${PORT}:8501`
        with PORT=8501 publishes on every interface, and the Dagster UI can
        start and kill jobs.
        """
        for name, svc in compose["services"].items():
            for mapping in svc.get("ports", []):
                assert str(mapping).startswith("127.0.0.1:"), (
                    f"{name} publishes {mapping} beyond loopback"
                )

    def test_the_container_side_of_each_mapping_is_fixed(self, compose):
        """Only the host side moves. The container listens where its command
        says it listens, and a variable there would decouple the two."""
        for name, svc in compose["services"].items():
            for mapping in svc.get("ports", []):
                container_side = str(mapping).rsplit(":", 1)[1]
                assert container_side.isdigit(), (
                    f"{name} varies the container port ({mapping}); only the "
                    "host side may move"
                )


class TestTheProjectNameIsPinned:
    def test_compose_names_the_project(self, compose):
        assert compose.get("name"), (
            "the project name comes from the directory basename, so the volume "
            "names depend on where somebody cloned it"
        )

    def test_it_is_the_name_the_host_already_uses(self, compose):
        """Changing this orphans the database. The running deployment reports
        `com.docker.compose.project=bonuschef` with volumes
        `bonuschef_pg_data` and `bonuschef_dagster_home`; any other value here
        makes `compose up` create empty volumes beside the real ones and start
        a stack with no data, which looks like a fresh install rather than an
        error.
        """
        assert compose["name"] == "bonuschef", (
            "production's volumes are prefixed bonuschef_; a different project "
            "name silently starts an empty database"
        )

    def test_the_volumes_are_still_the_two_that_hold_state(self, compose):
        assert set(compose["volumes"]) == {"pg_data", "dagster_home"}
