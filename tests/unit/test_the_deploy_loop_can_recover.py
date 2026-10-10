"""Three bugs that together wedged the deploy loop, found by watching a real
release fail.

v1.41.0 was tagged, the timer fired, and production stayed on v1.40.2 with the
mechanism reporting success once a minute. None of the three is hypothetical
and none was caught by a test, because each lived in the seam between two
scripts that were individually correct.

1. **deploy.sh rewrote itself mid-run.** Bash reads a script incrementally, so
   `git checkout` of a release that changed deploy.sh left the process running
   a mixture of both versions. The old half ran `up -d --build` against the new
   docker-compose.yml, which has no build section, so Compose tried to *pull*
   `bonuschef:v1.41.0` from Docker Hub.

2. **A failed build looked like a successful one.** `eval "$(...)"` discards the
   substitution's exit status, so `set -e` saw nothing and the deploy fell
   through to `up`, which then produced "pull access denied" - a message about
   a registry this project does not use.

3. **auto-deploy compared the checkout, not the running stack.** deploy.sh
   checks the tag out before it builds, so a deploy failing after that point
   leaves HEAD at the new tag. Every later tick compared the new tag with
   itself and did nothing. It could not self-heal, because the runner is only
   refreshed by a deploy that succeeds.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "scripts" / "deploy.sh"
AUTO = REPO_ROOT / "scripts" / "auto-deploy.sh"


def _code(path: Path) -> str:
    """The script with its comments removed.

    Ordering assertions must read the commands, not the prose about them. The
    comments here explain `docker compose up -d` and `up -d --build` at length,
    and a plain `text.index(...)` finds the explanation first - which is how a
    guard comes to assert something about a sentence.
    """
    return "\n".join(
        line
        for line in path.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )


class TestDeployRereadsItselfAfterCheckout:
    def test_it_re_execs_after_moving_head(self):
        text = _code(DEPLOY)
        checkout = text.index("git checkout -q --detach")
        reexec = text.index('exec bash "$0"')
        assert checkout < reexec, (
            "the re-exec must come after the checkout, or it re-reads the same "
            "file it was already running"
        )

    def test_the_re_exec_happens_before_anything_is_built_or_started(self):
        """The point is that the build and the start come from the new file."""
        text = _code(DEPLOY)
        reexec = text.index('exec bash "$0"')
        assert reexec < text.index("build-image.sh")
        assert reexec < text.index("docker compose up")

    def test_it_cannot_recurse(self):
        text = _code(DEPLOY)
        assert "BONUSCHEF_DEPLOY_REEXEC" in text
        guard = text[text.index("BONUSCHEF_DEPLOY_REEXEC") :]
        assert "exec bash" in guard[:400], "the guard must gate the exec"

    def test_the_arguments_survive_the_re_exec(self):
        """Without "$@" the second pass has no tag and exits 64 on usage."""
        text = DEPLOY.read_text()
        assert 'exec bash "$0" "$@"' in text

    def test_it_actually_re_execs_once_and_only_once(self, tmp_path):
        """Run the real control flow with a stub git and docker, and count how
        many times the script enters. Twice is correct; a loop would hang."""
        work = tmp_path / "w"
        (work / "scripts").mkdir(parents=True)
        (work / "scripts" / "deploy.sh").write_bytes(DEPLOY.read_bytes())
        (work / ".env").write_text("x=1\n")
        counter = work / "entries"

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        # git: the tag exists, HEAD is at it, the tree is clean.
        (bin_dir / "git").write_text(
            "#!/usr/bin/env bash\n"
            'case "$*" in\n'
            '  *"rev-parse -q --verify"*) exit 0 ;;\n'
            '  "rev-parse HEAD") echo deadbeef ;;\n'
            '  *"rev-parse refs/tags/"*) echo deadbeef ;;\n'
            "  *) exit 0 ;;\n"
            "esac\n"
        )
        # docker: nothing running, nothing to inspect.
        (bin_dir / "docker").write_text("#!/usr/bin/env bash\nexit 1\n")
        # version.sh is invoked through bash, so it must exist.
        (work / "scripts" / "version.sh").write_text(
            "#!/usr/bin/env bash\necho version=v1.0.0\necho commit=deadbeef\n"
        )
        # build-image.sh: record each entry of deploy.sh via its own invocation.
        (work / "scripts" / "build-image.sh").write_text(
            f"#!/usr/bin/env bash\necho x >> {counter}\necho image=bonuschef:v1.0.0\n"
        )
        for path in bin_dir.iterdir():
            path.chmod(0o755)

        result = subprocess.run(
            ["bash", "scripts/deploy.sh", "v1.0.0"],
            cwd=work,
            capture_output=True,
            text=True,
            env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)},
            timeout=60,
        )
        # The image check fails (stub docker exits 1), which is the correct
        # refusal - what matters here is that build ran exactly once, so the
        # script entered twice and stopped.
        assert counter.exists(), f"build-image.sh never ran: {result.stderr}"
        assert counter.read_text().count("x") == 1, (
            "build-image.sh ran more than once, so the re-exec is recursing"
        )
        assert "re-reading deploy.sh" in result.stdout


class TestAFailedBuildStopsTheDeploy:
    def test_the_build_status_is_checked(self):
        """`eval "$(...)"` discards it: `eval "$(false)"` is `eval ""`, which
        succeeds, so `set -e` sees nothing wrong."""
        text = DEPLOY.read_text()
        assert 'eval "$(bash ./scripts/build-image.sh' not in text, (
            "the build's exit status is discarded by the command substitution"
        )
        assert 'if ! build_output="$(bash ./scripts/build-image.sh' in text

    def test_a_missing_image_is_named_as_such(self):
        """Compose's answer to a missing image is to reach for a registry, and
        the message sends the reader looking for credentials rather than for a
        build failure:

            Image bonuschef:v1.41.0 Error pull access denied for bonuschef,
            repository does not exist or may require 'docker login'
        """
        text = _code(DEPLOY)
        assert "docker image inspect" in text
        check = text.index("docker image inspect")
        assert check < text.index("docker compose up"), (
            "the image must be confirmed present before Compose is asked"
        )

    def test_it_refuses_rather_than_starting_anything(self, tmp_path):
        work = tmp_path / "w"
        (work / "scripts").mkdir(parents=True)
        (work / "scripts" / "deploy.sh").write_bytes(DEPLOY.read_bytes())
        (work / ".env").write_text("x=1\n")
        (work / "scripts" / "version.sh").write_text(
            "#!/usr/bin/env bash\necho version=v1.0.0\necho commit=deadbeef\n"
        )
        (work / "scripts" / "build-image.sh").write_text(
            "#!/usr/bin/env bash\necho 'build broke' >&2\nexit 1\n"
        )
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "git").write_text(
            "#!/usr/bin/env bash\n"
            'case "$*" in\n'
            '  *"rev-parse -q --verify"*) exit 0 ;;\n'
            '  "rev-parse HEAD") echo deadbeef ;;\n'
            '  *"rev-parse refs/tags/"*) echo deadbeef ;;\n'
            "  *) exit 0 ;;\n"
            "esac\n"
        )
        started = work / "started"
        (bin_dir / "docker").write_text(
            f"#!/usr/bin/env bash\n"
            f'case "$*" in *"compose up"*) echo up >> {started} ;; esac\nexit 1\n'
        )
        for path in bin_dir.iterdir():
            path.chmod(0o755)

        result = subprocess.run(
            ["bash", "scripts/deploy.sh", "v1.0.0"],
            cwd=work,
            capture_output=True,
            text=True,
            env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)},
            timeout=60,
        )
        assert result.returncode != 0
        assert "could not be built" in result.stderr
        assert not started.exists(), "it started the stack after a failed build"


class TestAutoDeployComparesWhatIsRunning:
    def test_it_reads_the_running_containers_version(self):
        """Not the checkout. deploy.sh moves HEAD before it builds, so a deploy
        failing after that point leaves the two disagreeing - and the checkout
        is the one that lies."""
        text = _code(AUTO)
        current = text[text.index('current="$(') : text.index('if [ "$current"')]
        assert "org.opencontainers.image.version" in current, (
            "auto-deploy still decides from the checkout, so a failed deploy "
            "is permanent"
        )
        assert "docker ps" in current

    def test_the_checkout_is_only_the_fallback(self):
        """It is still the best evidence when nothing is running at all - a
        host that has never deployed, or an image from before stamping."""
        text = _code(AUTO)
        current = text[text.index('current="$(') : text.index('if [ "$current"')]
        label = current.index("org.opencontainers.image.version")
        assert label < current.index("git describe"), (
            "the checkout must be consulted after the running stack, not before"
        )

    def test_a_non_answer_from_an_unstamped_image_falls_back(self):
        text = _code(AUTO)
        current = text[text.index('current="$(') : text.index('if [ "$current"')]
        assert "<no value>" in current, (
            "docker inspect prints <no value> for a missing label, which would "
            "then be compared against a tag and never match"
        )
        assert "unknown" in current

    @pytest.mark.parametrize(
        ("running", "latest", "should_deploy"),
        [
            ("v1.40.2", "v1.41.0", True),  # the case that was stuck
            ("v1.41.0", "v1.41.0", False),  # genuinely up to date
        ],
    )
    def test_the_decision_against_a_stub(
        self, tmp_path, running: str, latest: str, should_deploy: bool
    ):
        """The whole point, exercised: HEAD at the new tag while the containers
        run the old one must still deploy."""
        work = tmp_path / "w"
        (work / "scripts").mkdir(parents=True)
        (work / "scripts" / "auto-deploy.sh").write_bytes(AUTO.read_bytes())
        deployed = work / "deployed"
        (work / "scripts" / "deploy.sh").write_text(
            f'#!/usr/bin/env bash\necho "$1" >> {deployed}\n'
        )
        (work / "scripts" / "deploy.sh").chmod(0o755)

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        # HEAD is at the newest tag - the state a failed deploy leaves behind.
        (bin_dir / "git").write_text(
            "#!/usr/bin/env bash\n"
            'case "$*" in\n'
            f'  *"tag --list"*) echo {latest} ;;\n'
            f'  *"describe --tags --exact-match"*) echo {latest} ;;\n'
            '  *"rev-list --count"*) echo 0 ;;\n'
            '  *"status --porcelain"*) ;;\n'
            "  *) exit 0 ;;\n"
            "esac\n"
        )
        (bin_dir / "docker").write_text(
            "#!/usr/bin/env bash\n"
            'case "$*" in\n'
            '  *"ps -q"*) echo abc123 ;;\n'
            f"  *inspect*) echo {running} ;;\n"
            "  *) exit 0 ;;\n"
            "esac\n"
        )
        (bin_dir / "flock").write_text('#!/usr/bin/env bash\nshift 2; exec "$@"\n')
        for path in bin_dir.iterdir():
            path.chmod(0o755)

        subprocess.run(
            ["bash", "scripts/auto-deploy.sh"],
            cwd=work,
            capture_output=True,
            text=True,
            env={
                "PATH": f"{bin_dir}:/usr/bin:/bin",
                "HOME": str(tmp_path),
                "BONUSCHEF_CHECKOUT": str(work),
            },
            timeout=60,
        )
        assert deployed.exists() == should_deploy, (
            f"running={running} latest={latest}: "
            f"{'should have deployed' if should_deploy else 'should not have deployed'}"
        )
