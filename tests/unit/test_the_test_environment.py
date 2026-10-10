"""The second environment, and the three rules that keep it from reaching
production.

It exists so a change can be watched working before the people who were
invited see it. That much is convenience. The rules are not:

- it holds no Albert Heijn credential, because there is one credential and
  refreshing it may rotate the refresh token - the code persists the rotated
  one - so two environments refreshing it would invalidate each other's, and
  the symptom is production's prices quietly ceasing to update;
- it cannot reach production's database, because an environment for trying
  things out is one where destructive commands get run;
- it is not published, because unfinished work and a copy of production's
  accounts are exactly what it holds.

The file is standalone rather than a Compose override, because a merge cannot
remove a service and the pipeline has to be absent rather than switched off.
That buys duplication, so the drift between the two files is asserted here
field by field.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_FILE = REPO_ROOT / "docker-compose.yml"
TEST_FILE = REPO_ROOT / "docker-compose.test.yml"
PROD_ENV = REPO_ROOT / ".env.example"
TEST_ENV = REPO_ROOT / ".env.test.example"

# Anything that reaches Albert Heijn, or that carries what is needed to.
CREDENTIAL_KEYS = ("AH_REFRESH_TOKEN", "AH_ACCESS_TOKEN", "AH_TOKEN_FILE")
# The services that call the retailer, directly or by scheduling it.
PIPELINE_SERVICES = ("dagster-daemon", "dagster-webserver")


@pytest.fixture(scope="module")
def prod() -> dict:
    return yaml.safe_load(PROD_FILE.read_text())


@pytest.fixture(scope="module")
def test_stack() -> dict:
    return yaml.safe_load(TEST_FILE.read_text())


def _image_reference(service: dict) -> str | None:
    """The application image a service runs, without the `:?` error message.

    `${VAR:?set this and that}` carries human advice that is allowed to differ
    between the two files; the part that must match is everything up to it.
    """
    image = str(service.get("image", ""))
    if not image.startswith("bonuschef"):
        return None
    return re.sub(r":\?[^}]*\}", ":?}", image)


def _env_keys(path: Path) -> dict[str, str]:
    return {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in path.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


# --- the environment exists at all ------------------------------------------


class TestItIsASeparateStack:
    def test_the_file_exists(self):
        assert TEST_FILE.exists(), "there is nowhere to watch a change run"

    def test_it_has_its_own_project_name(self, prod, test_stack):
        assert test_stack.get("name"), "without a project name it collides"
        assert test_stack["name"] != prod["name"], (
            "one project name means one stack: starting this would replace "
            "production's containers rather than running beside them"
        )

    def test_it_is_not_a_compose_override(self, test_stack):
        """An override merges, and a merge cannot remove a service. Were this
        an override of the production file, the pipeline would come along with
        it - which is the one thing that must not happen."""
        assert "postgres" in test_stack["services"], (
            "a file that relies on being merged would not define postgres"
        )
        assert test_stack["services"]["postgres"].get("image"), (
            "an override would inherit the image rather than naming it"
        )

    def test_it_runs_the_same_image_as_production(self, prod, test_stack):
        """The point of building once. If this built its own, what was watched
        here would not be what production runs.

        Compared on the reference rather than the raw string: both say
        `bonuschef:${BONUSCHEF_VERSION:?...}` and the message after the `?`
        deliberately differs, because the two files are reached by different
        routes and the useful advice is not the same.
        """
        ours = {_image_reference(s) for s in test_stack["services"].values()}
        theirs = {_image_reference(s) for s in prod["services"].values()}
        ours.discard(None)
        theirs.discard(None)
        assert ours and ours == theirs, f"test runs {ours}, production runs {theirs}"

    def test_no_service_in_it_builds(self, test_stack):
        for name, svc in test_stack["services"].items():
            assert not svc.get("build"), f"{name} builds its own image"


# --- no credential, no pipeline ---------------------------------------------


class TestItNeverHoldsTheRetailerCredential:
    @pytest.mark.parametrize("service", PIPELINE_SERVICES)
    def test_the_pipeline_services_are_absent(self, test_stack, service: str):
        """Absent, not idle. A service present with no schedules is one
        `compose up <service>` from running, and the failure that follows is
        not a broken test environment - it is production's credential rotated
        out from under it."""
        assert service not in test_stack["services"], (
            f"{service} is defined in the test stack. Remove it; do not "
            "disable its schedules."
        )

    def test_absence_is_what_is_checked_not_configuration(self):
        """The guard above must be about presence.

        A check that accepted a daemon with no schedules would pass for a file
        one edit away from refreshing the credential, so this pins the
        distinction with a stack that is exactly that.
        """
        plausible = yaml.safe_load(
            """
            name: bonuschef-test
            services:
              dagster-daemon:
                image: bonuschef:v1
                environment:
                  DAGSTER_SCHEDULES_ENABLED: "false"
            """
        )
        with pytest.raises(AssertionError):
            TestItNeverHoldsTheRetailerCredential().test_the_pipeline_services_are_absent(
                plausible, "dagster-daemon"
            )

    @pytest.mark.parametrize("key", CREDENTIAL_KEYS)
    def test_the_compose_file_names_no_credential(self, test_stack, key: str):
        text = yaml.dump(test_stack)
        assert key not in text, f"{key} appears in the test stack"

    @pytest.mark.parametrize("key", CREDENTIAL_KEYS)
    def test_the_env_template_names_no_credential(self, key: str):
        assert key not in _env_keys(TEST_ENV), f"{key} is set in {TEST_ENV.name}"

    def test_it_does_not_share_the_token_file_volume(self, test_stack):
        """In production the portal shares the daemon's token file, and the
        comment there explains why: without it the portal bootstraps its own
        token from .env and rotates the credential out from under the daemon.
        Here there is no daemon and no token, so mounting anything would only
        create a path to one.
        """
        for name, svc in test_stack["services"].items():
            for mount in svc.get("volumes", []):
                assert "dagster_home" not in str(mount), (
                    f"{name} mounts the token volume"
                )

    def test_it_does_not_share_the_alerting_topic(self):
        """The topic is a capability URL and the operator's phone is on the
        other end. Test noise beside real alerts is how real alerts come to be
        ignored."""
        assert _env_keys(TEST_ENV).get("NTFY_TOPIC", "") == "", (
            "the test environment would notify the operator's phone"
        )

    def test_the_rule_is_written_down_where_it_is_enforced(self):
        """A rule whose reason is only in a spec gets undone by whoever is
        looking at the file instead."""
        text = TEST_FILE.read_text().lower()
        assert "rotat" in text, "the compose file does not say why"
        assert "credential" in text


# --- its own data, and only its own -----------------------------------------


class TestItCannotTouchProductionsData:
    def test_it_runs_its_own_database(self, test_stack):
        assert "postgres" in test_stack["services"]
        assert test_stack["services"]["postgres"]["image"].startswith("postgres:")

    def test_the_portal_points_at_that_database(self, test_stack):
        env = test_stack["services"]["streamlit"]["environment"]
        assert env["PG_HOST"] == "postgres", (
            f"the test portal connects to {env['PG_HOST']!r}"
        )
        assert str(env["PG_PORT"]) == "5432", (
            "5455 would be production's published port rather than this "
            "project's own service"
        )

    def test_productions_database_is_not_addressable_from_it(self, test_stack):
        """Unreachable rather than merely unused. Production's Postgres is
        published on 127.0.0.1:5455 of the host, which is not the container's
        loopback - so there is no route, provided nothing here names the host.
        """
        text = yaml.dump(test_stack)
        for route in ("host.docker.internal", "network_mode: host", "5455"):
            assert route not in text, (
                f"{route!r} in the test stack opens a path to production's database"
            )
        for name, svc in test_stack["services"].items():
            assert not svc.get("network_mode"), f"{name} overrides its network"
            assert not svc.get("external_links"), name

    def test_its_database_does_not_live_in_productions_volume(self, prod, test_stack):
        """The named volumes are `bonuschef_pg_data` and
        `bonuschef_dagster_home`; a second project reaching one of those would
        be two Postgres instances on one data directory, which corrupts it.
        """
        mounts = [
            str(m)
            for svc in test_stack["services"].values()
            for m in svc.get("volumes", [])
        ]
        assert mounts, "the test database has no storage at all"
        for mount in mounts:
            source = mount.split(":", 1)[0]
            assert source not in prod.get("volumes", {}), (
                f"{mount} shares production's named volume"
            )
            assert not source.startswith("bonuschef_"), mount

    def test_its_storage_has_no_default(self, test_stack):
        """The only space available without being told is production's 16 GiB
        rootfs, which has 6.2 GiB free. A 1.1 GB restore and a 1.1 GB dump
        beside it is how a test environment takes production down, so refusing
        to start is the correct behaviour until somebody points it at the SSD.
        """
        mount = next(
            str(m)
            for m in test_stack["services"]["postgres"]["volumes"]
            if "postgresql/data" in str(m)
        )
        assert "${" in mount, f"{mount} is a literal path"
        assert ":-" not in mount and ":=" not in mount, (
            f"{mount} defaults its location, so it could land on production's disk"
        )
        assert ":?" in mount, f"{mount} must refuse rather than guess"

    def test_the_two_databases_do_not_share_a_password_default(self):
        """Not secrecy - both are on one host behind one boundary. So that a
        connection string copied from the wrong terminal fails to authenticate
        instead of succeeding against the database you did not mean.
        """
        prod_pw = _env_keys(PROD_ENV).get("POSTGRES_PASSWORD")
        test_pw = _env_keys(TEST_ENV).get("POSTGRES_PASSWORD")
        assert prod_pw and test_pw
        assert prod_pw != test_pw, (
            "the templates share a password, so the first thing anybody does "
            "is make the two databases interchangeable"
        )

    def test_the_test_template_keeps_its_passwords_consistent(self):
        """Three keys, one value, as production's template already warns. A
        mismatch here surfaces as authentication failures that look like the
        database being down."""
        env = _env_keys(TEST_ENV)
        values = {
            env[key]
            for key in (
                "POSTGRES_PASSWORD",
                "PG_PASSWORD",
                "DESTINATION__POSTGRES__CREDENTIALS__PASSWORD",
            )
            if key in env
        }
        assert len(values) == 1, f"the template sets {len(values)} passwords: {values}"


# --- not published ----------------------------------------------------------


class TestItIsNotPublished:
    def test_every_port_binds_to_loopback(self, test_stack):
        published = [
            (name, str(m))
            for name, svc in test_stack["services"].items()
            for m in svc.get("ports", [])
        ]
        assert published, "expected published ports on loopback"
        for name, mapping in published:
            assert mapping.startswith("127.0.0.1:"), (
                f"{name} publishes {mapping} beyond loopback"
            )

    def test_its_ports_do_not_collide_with_productions(self, prod, test_stack):
        """Whichever started first would hold the port and the other would
        fail to start - or worse, the operator would open 8501 believing it to
        be the test environment."""

        def host_ports(stack: dict) -> set[str]:
            found = set()
            for svc in stack["services"].values():
                for mapping in svc.get("ports", []):
                    default = re.search(r":-(\d+)\}", str(mapping))
                    if default:
                        found.add(default.group(1))
            return found

        theirs, ours = host_ports(prod), host_ports(test_stack)
        assert ours, "no default ports found in the test stack"
        assert not (ours & theirs), f"both stacks default to {sorted(ours & theirs)}"

    def test_the_sign_in_wall_stays_up(self):
        """The copy carries production's accounts. Not published is not the
        same as not worth protecting."""
        assert _env_keys(TEST_ENV).get("BONUSCHEF_REQUIRE_SIGN_IN") == "1"

    def test_registration_is_closed(self):
        """An invite code here would let somebody create an account in the
        wrong environment and wonder why their recipes vanished."""
        assert _env_keys(TEST_ENV).get("BONUSCHEF_INVITE_CODE", "") == ""


# --- the duplication this file buys -----------------------------------------


class TestTheTwoFilesDoNotDrift:
    """Standalone means duplicated, and duplicated means wrong eventually.

    Only the services both stacks run, and only the fields where agreement is
    the point: the ones that differ - ports, project name, storage, the
    environment marker - are the reason there are two files.
    """

    SHARED = ("postgres", "streamlit")

    @pytest.mark.parametrize("service", SHARED)
    def test_both_stacks_define_it(self, prod, test_stack, service: str):
        assert service in prod["services"]
        assert service in test_stack["services"]

    @pytest.mark.parametrize("service", SHARED)
    def test_the_command_matches(self, prod, test_stack, service: str):
        """A portal started with different arguments is a different portal, and
        what was watched would not be what runs."""
        assert test_stack["services"][service].get("command") == prod["services"][
            service
        ].get("command"), f"{service} starts differently in the two environments"

    @pytest.mark.parametrize("service", SHARED)
    def test_the_health_probe_matches(self, prod, test_stack, service: str):
        """The probes took three attempts to get right, twice reporting healthy
        for a service that was not. A copy that missed a fix would report
        healthy here for a fault that production catches."""
        assert test_stack["services"][service].get("healthcheck") == prod["services"][
            service
        ].get("healthcheck"), f"{service}'s probe has drifted"

    @pytest.mark.parametrize("service", SHARED)
    def test_the_restart_policy_and_logging_match(self, prod, test_stack, service: str):
        for field in ("restart", "logging"):
            assert test_stack["services"][service].get(field) == prod["services"][
                service
            ].get(field), f"{service}'s {field} has drifted"

    def test_postgres_keeps_the_settings_that_were_learned_the_hard_way(
        self, prod, test_stack
    ):
        """shm_size and stop_grace_period are both scar tissue: 64 MB of
        /dev/shm fails parallel queries with a message that reads as a full
        disk, and a checkpoint killed at the 10s default means WAL recovery on
        the next boot."""
        for field in ("shm_size", "stop_grace_period", "image"):
            assert test_stack["services"]["postgres"].get(field) == prod["services"][
                "postgres"
            ].get(field), f"postgres {field} has drifted"

    def test_the_copy_did_not_bring_productions_environment_marker(
        self, prod, test_stack
    ):
        """The one field that must differ, asserted so a copy-paste cannot
        quietly make the test environment claim to be production."""
        assert (
            test_stack["services"]["streamlit"]["environment"]["BONUSCHEF_ENVIRONMENT"]
            == "test"
        )
        prod_env = prod["services"]["streamlit"].get("environment") or {}
        assert "BONUSCHEF_ENVIRONMENT" not in prod_env, (
            "production must carry no marker; an invited person has one "
            "environment and labelling it is noise"
        )


class TestNoEnvFileCanBeCommitted:
    """`.env` in .gitignore matches that exact name and nothing else.

    So `.env.test`, which carries the test environment's database password, was
    committable. Found by running `git check-ignore` before creating the file
    rather than after - which is the only reason this is a test and not an
    incident.

    The templates are the exception: they are the documentation of what has to
    be set, and they carry placeholders.
    """

    SECRET_FILES = (".env", ".env.test", ".env.production", ".env.local")
    TEMPLATES = (".env.example", ".env.test.example")

    @staticmethod
    def _ignored(name: str) -> bool:
        import subprocess

        return (
            subprocess.run(
                ["git", "check-ignore", "-q", name],
                cwd=REPO_ROOT,
                capture_output=True,
            ).returncode
            == 0
        )

    @pytest.mark.parametrize("name", SECRET_FILES)
    def test_a_real_env_file_is_ignored(self, name: str):
        assert self._ignored(name), (
            f"{name} would be committed. It holds a database password."
        )

    @pytest.mark.parametrize("name", TEMPLATES)
    def test_the_templates_are_not_ignored(self, name: str):
        """They are how a deployment knows what to set. Ignoring them would
        make the repo unable to describe its own configuration."""
        assert not self._ignored(name), f"{name} must stay tracked"

    def test_the_templates_exist(self):
        for name in self.TEMPLATES:
            assert (REPO_ROOT / name).exists(), name

    def test_no_env_file_is_actually_tracked_right_now(self):
        """The rule above is about what git would do. This is about what git
        has already done - a file committed before the rule existed stays
        tracked, and .gitignore has no opinion about it."""
        import subprocess

        tracked = subprocess.run(
            ["git", "ls-files", ".env*"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        ).stdout.split()
        assert set(tracked) <= set(self.TEMPLATES), (
            f"these env files are committed: {sorted(set(tracked) - set(self.TEMPLATES))}"
        )
