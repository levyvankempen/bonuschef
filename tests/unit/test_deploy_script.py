"""The deploy script's guards.

Each guard here corresponds to something that has already gone wrong on the
real host, recorded in docs/deployment.md. The script exists so those lessons
are enforced rather than remembered.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "deploy.sh"


def _run(*args, cwd: Path | None = None):
    return subprocess.run(
        ["bash", str(DEPLOY), *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
    )


def test_the_script_is_syntactically_valid():
    assert subprocess.run(["bash", "-n", str(DEPLOY)]).returncode == 0


def test_it_is_executable():
    assert DEPLOY.stat().st_mode & 0o111, "not executable; deploying would need `bash`"


def test_naming_no_version_is_refused_and_suggests_some():
    """Deploying "whatever is here" is the habit this replaces."""
    r = _run()
    assert r.returncode != 0
    assert "usage" in r.stderr.lower()
    assert "available" in r.stderr.lower(), "refusing without helping is unkind"


@pytest.fixture
def repo(tmp_path):
    """A checkout with one tag and one branch, and no Docker anywhere."""
    import os

    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    for s in ("deploy.sh", "version.sh"):
        dst = r / "scripts" / s
        dst.write_text((ROOT / "scripts" / s).read_text())
        dst.chmod(0o755)
    (r / "pyproject.toml").write_text('version = "0.0.1"\n')
    (r / "docker-compose.yml").write_text("services: {}\n")
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    for cmd in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "-A"],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        ["git", "tag", "v0.0.1"],
        # `git fetch origin` must have something to talk to.
        ["git", "remote", "add", "origin", str(r)],
    ):
        subprocess.run(cmd, cwd=r, check=True, capture_output=True, env=env)
    return r


def _deploy(repo: Path, *args):
    return subprocess.run(
        ["bash", str(repo / "scripts" / "deploy.sh"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_a_branch_is_refused(repo):
    """Deploying `main` is how you get back to not knowing what is running:
    it names something different tomorrow, while the image stamp claims to
    describe a fixed thing."""
    r = _deploy(repo, "main")
    assert r.returncode != 0
    assert "not a tag" in r.stderr


def test_a_bare_commit_is_refused(repo):
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    r = _deploy(repo, sha)
    assert r.returncode != 0, "a commit is not a released version"


def test_a_missing_tag_is_refused(repo):
    r = _deploy(repo, "v9.9.9")
    assert r.returncode != 0
    assert "not a tag" in r.stderr


def test_deploying_without_an_env_file_is_refused(repo):
    """The services would start on their defaults -- which for Postgres means
    a well-known password on a database holding everything that cannot be
    rebuilt."""
    r = _deploy(repo, "v0.0.1")
    assert r.returncode != 0
    assert ".env" in r.stderr
    assert "defaults" in r.stderr.lower()


def test_a_valid_tag_gets_past_the_guards(repo):
    """With .env present it proceeds to the build, which is as far as this
    can go without Docker. Reaching that point is the check."""
    (repo / ".env").write_text("PG_USER=x\n")
    r = _deploy(repo, "v0.0.1")
    assert "deploying v0.0.1" in r.stdout, (
        f"stopped before building.\nstdout={r.stdout}\nstderr={r.stderr}"
    )


def test_the_script_refuses_rather_than_guessing(repo):
    """Every refusal above must be a non-zero exit, so a deployment that did
    not happen cannot be mistaken for one that did."""
    for args in ((), ("main",), ("v9.9.9",)):
        assert _deploy(repo, *args).returncode != 0


def test_a_deploy_reclaims_the_cache_it_creates():
    """Every build leaves layers behind.

    That was tolerable while deploys were occasional and manual. With the
    auto-deploy timer it happens on every release, and the cache reached 5.6 GB
    of a 16 GB rootfs - 100% reclaimable, and larger than the database, the
    images and the logs combined.

    For proportion: the Dagster event_logs that dagster.yaml warns about were
    41 MB at the same moment.
    """
    body = DEPLOY.read_text()
    assert "docker builder prune" in body, (
        "the deploy builds every time and never reclaims the cache"
    )
    # The build moved out of `up` and into build-image.sh, so the anchor moves
    # with it. Same invariant: reclaim after the step that fills the cache.
    assert body.index("build-image.sh") < body.index("docker builder prune"), (
        "the cache is pruned before the build that creates it"
    )


def test_reclaiming_keeps_recent_cache():
    """-a would start every rebuild cold. The aim is to bound growth, not to
    throw away the week of cache that makes a rebuild quick."""
    body = DEPLOY.read_text()
    assert "--filter until=" in body, "the prune is unbounded"
    assert "builder prune -af" not in body


def test_a_failed_prune_does_not_fail_the_deploy():
    """The stack is already up by then. Losing a deploy over housekeeping
    would be the tail wagging the dog."""
    body = DEPLOY.read_text()
    line = next(row for row in body.splitlines() if "docker builder prune" in row)
    assert "|| true" in line, line


class TestTheUnitsAreRefreshedToo:
    """deploy/systemd/ was a committed deployment path that never applied.

    The runner script was reinstalled on every deploy; the systemd files beside
    it were not. So changing the timer's interval in the repository changed
    nothing on the host until somebody copied it by hand - which is the same
    shape as the account schema that was correct, idempotent and called by
    nothing. Found by changing the interval and then asking whether it would
    take effect.
    """

    SCRIPT = Path("scripts/deploy.sh")

    def test_the_units_are_installed_on_a_deploy(self):
        body = self.SCRIPT.read_text()
        assert "deploy/systemd" in body
        assert "daemon-reload" in body

    def test_only_when_they_differ(self):
        """A deploy that rewrites unchanged files churns systemd for nothing."""
        body = self.SCRIPT.read_text()
        units = body[body.index("UNITS=") :]
        assert "cmp -s" in units

    def test_the_timer_is_restarted_but_not_the_service(self):
        """A changed interval must apply now rather than after a reboot - but
        the service is what is running this script."""
        body = self.SCRIPT.read_text()
        units = body[body.index("UNITS=") :]
        assert "restart bonuschef-autodeploy.timer" in units
        assert "restart bonuschef-autodeploy.service" not in units

    def test_it_does_nothing_where_it_cannot(self, tmp_path):
        """The developer case has no /etc/systemd/system to write to, and a
        deploy there must not fail on that."""
        body = self.SCRIPT.read_text()
        units = body[body.index("UNITS=") :]
        assert '-w "$UNITS"' in units, "guarded on writability"
        assert "BONUSCHEF_SYSTEMD_DIR" in body, "and overridable for a test"

    def test_a_run_against_a_scratch_directory_installs_them(self, tmp_path):
        """Exercised rather than asserted about: the guard is only worth having
        if the copy underneath it works."""
        import subprocess

        units = tmp_path / "systemd"
        units.mkdir()
        script = f"""
        set -euo pipefail
        cd {Path.cwd()}
        UNITS="{units}"
        for unit in ./deploy/systemd/bonuschef-*; do
            [ -f "$unit" ] || continue
            if ! cmp -s "$unit" "$UNITS/$(basename "$unit")" 2>/dev/null; then
                install -m 0644 "$unit" "$UNITS/$(basename "$unit")"
            fi
        done
        """
        subprocess.run(["bash", "-c", script], check=True)
        installed = sorted(p.name for p in units.iterdir())
        assert installed, "the units must actually land"
        assert any(n.endswith(".timer") for n in installed), installed
