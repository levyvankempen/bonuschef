"""The unattended half of deployment.

This runs on a timer with nobody watching, so every branch here is a decision
made in an empty room. The dangerous ones are not the failures -- they are the
cases where acting would be wrong and doing nothing is right.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
UNITS = ROOT / "deploy" / "systemd"


def _in_flight_exit_code() -> int:
    """What deploy.sh actually exits with when a run is in flight.

    Read from the script rather than written here. The recorder below stands
    in for deploy.sh because the real one drives Docker - but a stand-in that
    invents the interface it is standing in for cannot notice the interface
    changing, and this number is the whole contract between the two scripts.
    """
    source = (SCRIPTS / "deploy.sh").read_text()
    marker = source.index("run(s) in flight")
    match = re.search(r"exit (\d+)", source[marker : marker + 400])
    assert match, "deploy.sh no longer exits with a code when a run is in flight"
    return int(match.group(1))


IN_FLIGHT_EXIT = _in_flight_exit_code()


@dataclass
class Server:
    """The deployment host, and the upstream it pulls from."""

    path: Path
    seed: Path
    log: Path


def _git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, env=env, check=True
    ).stdout.strip()


@pytest.fixture
def server(tmp_path):
    """A checkout standing in for the deployment host, with a real upstream.

    The upstream is a separate bare repository rather than the checkout itself,
    because the interesting cases are precisely the ones where the two
    disagree about which tags exist.

    `deploy.sh` is replaced with a recorder: the real one drives Docker, which
    is not available here and is not what these tests are about.
    """
    upstream = tmp_path / "upstream.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(upstream)], check=True
    )

    seed = tmp_path / "seed"
    (seed / "scripts").mkdir(parents=True)
    for s in ("auto-deploy.sh", "version.sh"):
        dst = seed / "scripts" / s
        dst.write_text((SCRIPTS / s).read_text())
        # Set the mode before committing. git tracks the executable bit, so
        # chmod-ing after the clone would show as a modification and the
        # script would correctly refuse to deploy over a dirty tree.
        dst.chmod(0o755)
    recorder = seed / "scripts" / "deploy.sh"
    recorder.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$1" >> "${DEPLOY_LOG:?}"\n'
        'exit "${FAKE_DEPLOY_STATUS:-0}"\n'
    )
    recorder.chmod(0o755)
    (seed / "pyproject.toml").write_text('version = "0.0.1"\n')
    _git(seed, "init", "-q", "-b", "main")
    _git(seed, "add", "-A")
    _git(seed, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "one")
    _git(seed, "tag", "v1.0.0")
    _git(seed, "remote", "add", "origin", str(upstream))
    _git(seed, "push", "-q", "origin", "main", "--tags")

    repo = tmp_path / "server"
    subprocess.run(
        ["git", "clone", "-q", str(upstream), str(repo)],
        check=True,
        capture_output=True,
    )
    _git(repo, "checkout", "-q", "--detach", "v1.0.0")
    return Server(path=repo, seed=seed, log=tmp_path / "deployed.log")


def _tick(server: Server, **env):
    repo = server.path
    return subprocess.run(
        ["bash", str(repo / "scripts" / "auto-deploy.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "DEPLOY_LOG": str(server.log),
            **env,
        },
    )


def _deployed(server: Server) -> list[str]:
    """What the recorder saw.

    The log lives outside the checkout on purpose: written inside it, it would
    be an untracked file, the script would correctly refuse to deploy over a
    dirty tree, and every test after the first would be measuring the fixture
    rather than the script.
    """
    log = server.log
    return log.read_text().split() if log.exists() else []


def _release(repo: Server, tag: str):
    """Cut a new release upstream, as the Release workflow would."""
    seed = repo.seed
    (seed / "pyproject.toml").write_text(f'version = "{tag.lstrip("v")}"\n')
    _git(seed, "add", "-A")
    _git(seed, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", tag)
    _git(seed, "tag", tag)
    _git(seed, "push", "-q", "origin", "main", "--tags")


def test_nothing_to_do_is_silent_and_successful(server):
    """A tick with no new release must exit 0. A timer that reports failure
    for routine inaction gets muted, and then the real failure is invisible
    too."""
    r = _tick(server)
    assert r.returncode == 0
    assert "up to date" in r.stdout
    assert _deployed(server) == [], "deployed without a new release"


def test_a_new_release_is_deployed(server):
    _release(server, "v1.1.0")
    r = _tick(server)
    assert r.returncode == 0
    assert _deployed(server) == ["v1.1.0"]


def test_the_same_release_is_not_deployed_twice(server):
    _release(server, "v1.1.0")
    _tick(server)
    _git(
        server.path, "checkout", "-q", "--detach", "v1.1.0"
    )  # as deploy.sh would leave it
    _tick(server)
    assert _deployed(server) == ["v1.1.0"], "redeployed a release already running"


def test_versions_are_ordered_as_versions_not_as_text(server):
    """v1.10.0 is newer than v1.9.0; sorted as strings it is not. Getting this
    wrong means the timer silently stops upgrading after v1.9.0."""
    _release(server, "v1.9.0")
    _tick(server)
    _git(server.path, "checkout", "-q", "--detach", "v1.9.0")
    _release(server, "v1.10.0")
    _tick(server)
    assert _deployed(server)[-1] == "v1.10.0", "string ordering stopped the upgrade"


def test_a_tag_that_exists_only_here_does_not_become_the_target(server):
    """`git tag --list` reads local tags, so a tag made by hand on the box --
    or one left behind after being deleted upstream -- would otherwise be
    picked as "the newest release" and deployed. Upstream is the authority on
    what has been released."""
    _git(server.path, "tag", "v9.0.0")
    _release(server, "v1.1.0")
    r = _tick(server)
    assert r.returncode == 0
    assert _deployed(server) == ["v1.1.0"], (
        f"deployed a local-only tag: {_deployed(server)}"
    )
    assert "v9.0.0" not in _git(server.path, "tag", "--list")


def test_an_untagged_head_recovers_to_the_newest_release(server):
    """HEAD at no known tag -- a hand-made commit, a tag deleted upstream.
    Reconciling towards the newest release is the recovery."""
    _git(server.path, "checkout", "-q", "--detach", "HEAD")
    (server.path / "notes.txt").write_text("hand-made\n")
    _git(server.path, "add", "-A")
    _git(
        server.path,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        "hand",
    )
    _release(server, "v1.1.0")
    r = _tick(server)
    assert r.returncode == 0
    assert _deployed(server) == ["v1.1.0"]


def test_a_dirty_tree_is_left_alone(server):
    """Someone is debugging on the box. `git checkout --detach` would discard
    their work without asking."""
    _release(server, "v1.1.0")
    (server.path / "pyproject.toml").write_text('version = "hand-edited"\n')
    r = _tick(server)
    assert r.returncode == 0
    assert "not clean" in r.stdout
    assert _deployed(server) == [], "discarded someone's uncommitted work"


def test_a_run_in_flight_is_not_a_failure(server):
    """deploy.sh exits 75 when a Dagster run is in progress, because
    rebuilding kills the run worker and wedges the queue. That happens several
    times a day; treating it as a failure would train the operator to ignore
    the alert."""
    _release(server, "v1.1.0")
    r = _tick(server, FAKE_DEPLOY_STATUS=str(IN_FLIGHT_EXIT))
    assert r.returncode == 0, "an in-flight run was reported as a failure"
    assert "retry" in r.stdout


def test_a_real_failure_is_reported(server):
    """Everything else must surface. systemd marks the unit failed and it
    shows in `systemctl --failed`."""
    _release(server, "v1.1.0")
    r = _tick(server, FAKE_DEPLOY_STATUS="1")
    assert r.returncode != 0, "a failed deployment exited 0"
    assert "failed" in r.stdout


def test_the_timer_survives_the_server_being_off(server):
    """A release cut while the box is down must still be picked up."""
    timer = (UNITS / "bonuschef-autodeploy.timer").read_text()
    assert "Persistent=true" in timer


def test_the_units_point_at_the_deployed_checkout():
    unit = (UNITS / "bonuschef-autodeploy.service").read_text()
    assert "/opt/bonuschef/scripts/auto-deploy.sh" in unit
    assert "Type=oneshot" in unit, "a timer-driven unit must be oneshot"
    assert "docker.service" in unit, "deploying before Docker is up would fail"


def test_a_hung_build_cannot_block_the_timer_forever():
    unit = (UNITS / "bonuschef-autodeploy.service").read_text()
    assert "TimeoutStartSec=" in unit


# --- the deployer must outlive the releases it deploys --------------------


def test_the_unit_does_not_run_the_script_from_the_checkout():
    """The deployer used to be run straight out of scripts/. That made it part
    of the thing it deploys: a rollback to a release predating it deleted
    systemd's ExecStart target, and auto-deploy stopped permanently -- because
    recovering is exactly what it could no longer do.

    Observed on a real rollback to v1.3.1:
        Unable to locate executable '/opt/bonuschef/scripts/auto-deploy.sh'
    """
    unit = (UNITS / "bonuschef-autodeploy.service").read_text()
    exec_lines = [ln for ln in unit.splitlines() if ln.strip().startswith("ExecStart=")]
    assert exec_lines, "the unit has no ExecStart"
    for ln in exec_lines:
        target = ln.split("=", 1)[1].strip()
        assert "/opt/bonuschef" not in target, (
            f"ExecStart points inside the deployed checkout ({target}); a "
            "rollback would delete it"
        )


def test_deploying_refreshes_the_out_of_tree_runner(tmp_path):
    """Living outside the checkout would otherwise mean going stale. Every
    successful deploy copies the current script out."""
    deploy = (ROOT / "scripts" / "deploy.sh").read_text()
    assert "install -m 0755 ./scripts/auto-deploy.sh" in deploy, (
        "deploy.sh does not refresh the runner, so it would freeze at "
        "whatever version first installed it"
    )
    # and it must happen after the stack is up, not before
    assert deploy.index("docker compose up -d --build") < deploy.index(
        "install -m 0755"
    ), "the runner is refreshed before the deploy succeeds"


def test_the_runner_finds_the_checkout_from_outside_it(server, tmp_path):
    """Installed to /usr/local/bin, the script can no longer assume it sits
    inside the checkout. Resolving its own directory from there lands in
    /usr/local, and git fails with "not a git repository" - which is what the
    server did the moment the runner was moved out of the tree.

    The fixture's own tests run the script from inside a checkout, which is
    why they did not catch it.
    """
    installed = tmp_path / "bin"
    installed.mkdir()
    runner = installed / "bonuschef-autodeploy"
    runner.write_text((SCRIPTS / "auto-deploy.sh").read_text())
    runner.chmod(0o755)

    result = subprocess.run(
        ["bash", str(runner)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "BONUSCHEF_CHECKOUT": str(server.path),
            "DEPLOY_LOG": str(server.log),
        },
    )
    assert "not a git repository" not in (result.stdout + result.stderr)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "up to date" in result.stdout


def test_a_checkout_beside_the_script_still_wins(server):
    """The developer case: running scripts/auto-deploy.sh from a clone must
    operate on that clone, not on whatever BONUSCHEF_CHECKOUT says."""
    other = server.path.parent / "elsewhere"
    other.mkdir(exist_ok=True)
    result = subprocess.run(
        ["bash", str(server.path / "scripts" / "auto-deploy.sh")],
        cwd=server.path,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "BONUSCHEF_CHECKOUT": str(other),
            "DEPLOY_LOG": str(server.log),
        },
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "up to date" in result.stdout


def test_it_notices_when_main_is_ahead_of_the_newest_tag(server):
    """A failed release is invisible: main is correct, CI is green, and the
    only symptom is a tag that never appeared. The timer said "up to date" on
    every tick throughout, because as far as tags go it was.

    Two releases failed this way before anyone noticed.
    """
    # Commit to upstream main WITHOUT tagging it - a merged PR whose release
    # failed.
    seed = server.seed
    (seed / "notes.txt").write_text("merged, never released\n")
    _git(seed, "add", "-A")
    _git(seed, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "feat: x")
    _git(seed, "push", "-q", "origin", "main")

    r = _tick(server)
    assert r.returncode == 0, "an unreleased commit is not a deployment failure"
    assert "ahead of it" in r.stdout, (
        f"the timer did not notice main had moved without a release:\n{r.stdout}"
    )
    assert _deployed(server) == [], "it deployed something that was never tagged"


def test_it_stays_quiet_when_main_and_the_tag_agree(server):
    """The ordinary case must not start emitting a warning, or the signal is
    worthless within a week."""
    r = _tick(server)
    assert "ahead of it" not in r.stdout
    assert "up to date" in r.stdout
