"""One page that can see both environments, and the route that lets it.

The Beheer page has had a test-environment panel since the environment existed,
and it rendered nothing: it needs `BONUSCHEF_TEST_DATABASE_URL`, and there was
no route for that URL to resolve over. Measured from inside production's
container, both candidate routes were refused:

    from prod streamlit -> 127.0.0.1:5456     ConnectionRefusedError
    from prod streamlit -> 172.17.0.1:5456    ConnectionRefusedError

The first is the container's own loopback. The second is the docker bridge, and
it fails because the test database publishes on the *host's* loopback only -
which is exactly the isolation that makes the test environment unpublished, so
widening it would be the wrong trade.

So: one shared network, joined by production's portal and the test
environment's database and by nothing else. That asymmetry is the whole safety
property, and these tests hold it from all four sides. Three of the four are
about what is NOT on the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_FILE = REPO_ROOT / "docker-compose.yml"
TEST_FILE = REPO_ROOT / "docker-compose.test.yml"
DEPLOY = REPO_ROOT / "scripts" / "deploy.sh"
COPY = REPO_ROOT / "scripts" / "copy-to-test.sh"

SHARED = "monitor"
SHARED_NAME = "bonuschef-monitor"


@pytest.fixture(scope="module")
def prod() -> dict:
    return yaml.safe_load(PROD_FILE.read_text())


@pytest.fixture(scope="module")
def test_stack() -> dict:
    return yaml.safe_load(TEST_FILE.read_text())


def _networks(service: dict) -> set[str]:
    """The networks a service joins, from either compose spelling.

    A list (`- default`) and a mapping (`default:` with options) mean the same
    thing, and the two files use one each because only the test database needs
    an alias.
    """
    declared = service.get("networks")
    if declared is None:
        # No `networks:` key means the project default, and nothing else.
        return {"default"}
    return set(declared)


# --- the route exists -------------------------------------------------------


class TestTheRouteExists:
    def test_productions_portal_is_on_the_shared_network(self, prod):
        assert SHARED in _networks(prod["services"]["streamlit"]), (
            "the Beheer panel has no route to the test environment, so it "
            "renders nothing"
        )

    def test_the_test_database_is_on_it(self, test_stack):
        assert SHARED in _networks(test_stack["services"]["postgres"])

    def test_the_test_database_has_a_stable_alias(self, test_stack):
        """A container name changes if the project or service is renamed; an
        alias does not, so production's connection string can be written down
        once."""
        networks = test_stack["services"]["postgres"]["networks"]
        assert isinstance(networks, dict), "an alias needs the mapping form"
        aliases = (networks[SHARED] or {}).get("aliases") or []
        assert aliases, "no alias, so the URL would have to name a container"
        assert "test-postgres" in aliases

    def test_both_files_agree_on_the_network_name(self, prod, test_stack):
        for stack, label in ((prod, "production"), (test_stack, "test")):
            declared = stack["networks"][SHARED]
            assert declared.get("name") == SHARED_NAME, label
            assert declared.get("external") is True, (
                f"{label} would try to own the network; two projects cannot "
                "both create one"
            )


# --- and runs one way only --------------------------------------------------


class TestTheRouteRunsOneWayOnly:
    """Production reads the test environment. Nothing reads back.

    Each of these is an absence, which is why they are asserted rather than
    assumed: listing `networks:` on a service makes it join *only* those, so
    every one of these holds by construction right now and would stop holding
    the moment somebody adds a line for convenience.
    """

    def test_the_test_portal_is_not_on_the_shared_network(self, test_stack):
        """The requirement is that production's database is unreachable from
        this environment, not merely unused by it. A portal on the shared
        network has a route to whatever else is there."""
        assert SHARED not in _networks(test_stack["services"]["streamlit"]), (
            "the test portal is on the shared network, which gives the "
            "environment a path it is required not to have"
        )

    def test_productions_database_is_not_on_the_shared_network(self, prod):
        """The other half. Even if something in the test environment joined the
        network later, production's database would still not be on it."""
        assert SHARED not in _networks(prod["services"]["postgres"]), (
            "production's database is on the shared network, so anything that "
            "joins it can reach the data the invited people's accounts live in"
        )

    def test_the_pipeline_services_are_not_on_it_either(self, prod):
        """They hold the retailer credential. Nothing about monitoring needs
        them reachable from another project."""
        for name in ("dagster-webserver", "dagster-daemon"):
            assert SHARED not in _networks(prod["services"][name]), name

    def test_exactly_one_service_per_stack_is_on_it(self, prod, test_stack):
        """Stated as a count, so a second joiner has to be a deliberate edit to
        this test rather than a quiet addition to a compose file."""
        for stack, label in ((prod, "production"), (test_stack, "test")):
            on_it = [
                name
                for name, svc in stack["services"].items()
                if SHARED in _networks(svc)
            ]
            assert len(on_it) == 1, f"{label} has {on_it} on the shared network"

    def test_productions_portal_keeps_its_own_network(self, prod):
        """Listing networks explicitly means joining only those - so naming the
        shared one without `default` would cut the portal off from its own
        database and the Dagster webserver it launches jobs through."""
        assert "default" in _networks(prod["services"]["streamlit"])

    def test_the_test_database_keeps_its_own_network(self, test_stack):
        assert "default" in _networks(test_stack["services"]["postgres"])


# --- nothing is blocked by the network not existing -------------------------


class TestTheNetworkIsAlwaysThere:
    """`external: true` means something else has to create it, and whichever
    stack starts first must not fail because the other has never run."""

    @pytest.mark.parametrize("script", (DEPLOY, COPY), ids=lambda p: p.name)
    def test_the_entry_point_creates_it(self, script: Path):
        text = script.read_text()
        assert f"network create {SHARED_NAME}" in text, (
            f"{script.name} would fail on a host where the network is missing"
        )

    @pytest.mark.parametrize("script", (DEPLOY, COPY), ids=lambda p: p.name)
    def test_creating_it_tolerates_it_already_existing(self, script: Path):
        """Which is the normal case, not a failure."""
        line = next(
            line
            for line in script.read_text().splitlines()
            if f"network create {SHARED_NAME}" in line
        )
        assert "|| true" in line, f"{script.name}: {line.strip()}"

    def test_deploy_creates_it_before_starting_anything(self):
        text = "\n".join(
            line
            for line in DEPLOY.read_text().splitlines()
            if not line.lstrip().startswith("#")
        )
        assert text.index(f"network create {SHARED_NAME}") < text.index(
            "docker compose up"
        ), "the stack would start before the network it needs exists"

    def test_the_copy_creates_it_before_it_starts_the_test_stack(self):
        text = "\n".join(
            line
            for line in COPY.read_text().splitlines()
            if not line.lstrip().startswith("#")
        )
        assert text.index(f"network create {SHARED_NAME}") < text.index("compose -f")
