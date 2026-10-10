"""One image per version, built once, run by both environments.

Deploying used to be `docker compose up -d --build`: every host, and every
deploy, built independently. That is fine while there is one environment and
nobody compares two builds. It stops being fine the moment a change is supposed
to be watched working in one place and then promoted to another, because
"promote the version I watched" needs an artifact and there was none - only
source, rebuilt.

Two builds of one commit were genuinely not the same bytes. `uv sync --frozen`
pins the Python side exactly, but the base image was a floating tag, so a
fortnight's gap bought a different Debian and CPython patch level with nothing
in any diff to show it.

These tests hold the three halves in place: the base is pinned, compose runs a
named image rather than building one, and deploy reuses an image that already
exists for the version instead of rebuilding it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
DEPLOY = REPO_ROOT / "scripts" / "deploy.sh"
BUILD_IMAGE = REPO_ROOT / "scripts" / "build-image.sh"


def _logical_lines(text: str):
    """Shell lines, with backslash continuations joined.

    One command spread over two lines is one command. Scanning raw lines reads
    the second half of

        env BONUSCHEF_VERSION=verify-only \\
            docker compose -f ... up -d postgres

    as a bare `docker compose` call, which is how a correct runbook entry gets
    reported as a fault. Yields (line number of the start, joined text).
    """
    out, buffer, start = [], "", None
    for number, raw in enumerate(text.splitlines(), 1):
        if start is None:
            start = number
        buffer += raw.rstrip()
        if buffer.endswith("\\"):
            buffer = buffer[:-1] + " "
            continue
        out.append((start, buffer))
        buffer, start = "", None
    if buffer:
        out.append((start, buffer))
    return out


class TestTheBaseImageIsPinned:
    def test_every_from_names_a_digest(self):
        """A floating base is the one thing in this build that can change
        without appearing in a diff."""
        froms = [
            line.strip()
            for line in DOCKERFILE.read_text().splitlines()
            if line.strip().upper().startswith("FROM ")
        ]
        assert froms, "no FROM line found"
        for line in froms:
            assert "@sha256:" in line, (
                f"{line!r} names a mutable tag. Two builds of one commit then "
                "differ by whatever the tag moved to. Pin it:\n"
                "  docker buildx imagetools inspect <image>:<tag>"
            )

    def test_the_digest_is_well_formed(self):
        """A truncated or mistyped digest fails at build time on the host,
        which is the worst place to find out."""
        for digest in re.findall(r"@sha256:([0-9a-f]*)", DOCKERFILE.read_text()):
            assert len(digest) == 64, f"sha256:{digest} is not 64 hex characters"

    def test_the_tag_is_kept_alongside_the_digest(self):
        """`image@sha256:...` alone is legal and unreadable. Keeping the tag
        means a human can see which base this was meant to be, and the digest
        decides what it actually is."""
        for line in DOCKERFILE.read_text().splitlines():
            if "@sha256:" not in line or not line.strip().upper().startswith("FROM "):
                continue
            reference = line.split()[1]
            assert ":" in reference.split("@")[0], (
                f"{reference} drops the human-readable tag"
            )


class TestComposeRunsAnImageRatherThanBuildingOne:
    @pytest.fixture(scope="class")
    def services(self) -> dict:
        return yaml.safe_load(COMPOSE_FILE.read_text())["services"]

    def test_no_service_builds(self, services):
        building = [name for name, svc in services.items() if svc.get("build")]
        assert not building, (
            f"{building} build their own image. Then two environments run two "
            "artifacts from one commit and promotion means nothing. Build once "
            "with scripts/build-image.sh and reference `image:`."
        )

    def test_every_service_names_an_image(self, services):
        for name, svc in services.items():
            assert svc.get("image"), f"{name} has neither build nor image"

    def test_the_application_image_is_selected_by_version(self, services):
        """Not `:latest`, and not a bare name. `bonuschef` with no tag resolves
        to `bonuschef:latest`, which is whatever was built last - the opposite
        of running a known version."""
        ours = {
            name: svc["image"]
            for name, svc in services.items()
            if svc["image"].startswith("bonuschef")
        }
        assert ours, "expected the application services to share one image"
        for name, image in ours.items():
            assert "BONUSCHEF_VERSION" in image, (
                f"{name} runs {image}, which does not name a version"
            )
            assert not image.endswith(("latest", "bonuschef")), name

    def test_the_version_has_no_fallback_value(self, services):
        """`${BONUSCHEF_VERSION:-something}` would let a stack start on a
        default tag. If an image by that name happens to exist - left over from
        an earlier deploy - it starts, runs stale code, and reports the version
        it was stamped with. Refusing is the only safe answer."""
        for name, svc in services.items():
            image = svc["image"]
            if "BONUSCHEF_VERSION" not in image:
                continue
            assert ":-" not in image and ":=" not in image, (
                f"{name} defaults the version; a stale image would start silently"
            )
            assert ":?" in image, f"{name} must make the version mandatory"

    def test_all_application_services_run_the_same_image(self, services):
        """Three services from one image. Diverging would mean the portal and
        the daemon could be different versions, which is exactly the confusion
        the version stamp exists to prevent."""
        ours = {
            svc["image"]
            for svc in services.values()
            if svc["image"].startswith("bonuschef")
        }
        assert len(ours) == 1, (
            f"the application services run {len(ours)} images: {ours}"
        )


class TestBuildImageIsTheOnePlaceThatBuilds:
    def test_it_exists_and_is_executable(self):
        assert BUILD_IMAGE.exists()
        assert BUILD_IMAGE.stat().st_mode & 0o111, "not executable"

    def test_it_refuses_anything_that_is_not_a_tag(self):
        """The same rule deploy.sh applies. An image built from a branch is
        stamped with a name that means something different tomorrow."""
        text = BUILD_IMAGE.read_text()
        assert "refs/tags/" in text
        assert "rev-parse" in text

    def test_it_reuses_an_existing_image(self):
        """The whole point of promotion. Rebuilding on promote would discard
        the artifact that was watched and substitute a fresh one."""
        text = BUILD_IMAGE.read_text()
        assert "docker image inspect" in text, "no reuse check"
        assert "already built" in text

    def test_the_reuse_can_be_overridden(self):
        """A rebuild has to be possible, or a cache poisoned by a failed build
        needs a human deleting images by hand."""
        assert "BONUSCHEF_FORCE_BUILD" in BUILD_IMAGE.read_text()

    def test_only_the_image_line_goes_to_stdout(self):
        """Its caller evals stdout. A progress line there becomes a command,
        and `building` is not one."""
        text = BUILD_IMAGE.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("echo "):
                continue
            if "image=" in stripped:
                assert ">&2" not in stripped, "the one stdout line was sent to stderr"
            else:
                assert ">&2" in stripped, (
                    f"{stripped!r} writes progress to stdout, which its caller evals"
                )

    def test_the_build_itself_does_not_pollute_stdout(self):
        text = BUILD_IMAGE.read_text()
        build = text[text.index("docker build") :]
        body = build[: build.index("\n\n")] if "\n\n" in build else build
        assert ">&2" in body, "docker build's output would be eval'd by the caller"

    def test_it_stamps_the_version_and_commit(self):
        text = BUILD_IMAGE.read_text()
        assert "--build-arg" in text
        assert "BONUSCHEF_VERSION=" in text
        assert "BONUSCHEF_COMMIT=" in text


class TestDeployPromotesRatherThanRebuilds:
    def test_deploy_no_longer_passes_build(self):
        text = DEPLOY.read_text()
        up = [
            line
            for line in text.splitlines()
            if "docker compose up" in line and not line.strip().startswith("#")
        ]
        assert up, "no `docker compose up` in deploy.sh"
        for line in up:
            assert "--build" not in line, (
                "deploy still builds during `up`, so what runs is a rebuild "
                "rather than the artifact that was watched"
            )

    def test_deploy_builds_through_the_one_script(self):
        text = DEPLOY.read_text()
        assert "build-image.sh" in text, "deploy does not build the image at all"
        assert text.index("build-image.sh") < text.index("docker compose up"), (
            "the image must exist before the stack is started"
        )

    def test_the_inspection_before_checkout_can_still_parse_compose(self):
        """A trap found by running the deploy path. The in-flight check calls
        `docker compose`, which now cannot parse the file without
        BONUSCHEF_VERSION - and at that point the tag has not been checked out,
        so the real version is unknowable.

        Failing there is not loud: the check is wrapped in `|| echo 0`, so the
        deploy would conclude no runs are in flight and rebuild on top of a
        live Dagster job, which is the one thing the check exists to prevent.
        """
        text = DEPLOY.read_text()
        placeholder = text.index('export BONUSCHEF_VERSION="${BONUSCHEF_VERSION:-')
        first_compose = text.index("docker compose ps")
        assert placeholder < first_compose, (
            "the in-flight check runs before BONUSCHEF_VERSION is set, so it "
            "fails open and the deploy proceeds over a running job"
        )

    def test_the_real_version_replaces_the_placeholder_before_anything_starts(self):
        text = DEPLOY.read_text()
        real = text.index('export BONUSCHEF_VERSION="$version"')
        assert real < text.index("docker compose up"), (
            "the stack would start on the placeholder tag"
        )
        assert real < text.index("build-image.sh")


class TestTheDocumentedCommandsStillWork:
    """The cost of a mandatory version, and the thing that pays it.

    Compose interpolates at parse time, so `${BONUSCHEF_VERSION:?}` makes
    *every* command fail without it - `ps`, `logs` and `exec` included, none of
    which resolve an image. Verified against the deployment host:

        error while interpolating services.a.image:
        required variable BONUSCHEF_VERSION is missing a value

    Every documented recovery command is one of those, so making the version
    mandatory without this wrapper would have left the runbook broken while
    every test passed.
    """

    WRAPPER = REPO_ROOT / "scripts" / "compose.sh"

    def test_the_wrapper_exists_and_is_executable(self):
        assert self.WRAPPER.exists()
        assert self.WRAPPER.stat().st_mode & 0o111

    def test_it_supplies_the_variable_and_hands_off(self):
        text = self.WRAPPER.read_text()
        assert "export BONUSCHEF_VERSION" in text
        assert "exec docker compose" in text, "it must pass the arguments through"

    def test_it_reads_the_version_from_the_running_stack(self):
        """Not from `git describe` first: the checkout can sit at a different
        tag than the running stack, and these commands address the stack."""
        text = self.WRAPPER.read_text()
        label = text.index("org.opencontainers.image.version")
        assert label < text.index("version.sh"), (
            "the checkout must be the fallback, not the first answer"
        )

    def test_it_reads_the_label_rather_than_parsing_the_image_tag(self):
        """Before this change the images were named by Compose
        (`bonuschef-streamlit`), so a tag-parsing version answers nothing on a
        host that has not deployed since - which is every host, once. The OCI
        label has been stamped all along.
        """
        text = self.WRAPPER.read_text()
        assert "docker inspect" in text
        assert "org.opencontainers.image.version" in text

    def test_it_rejects_a_non_answer_from_an_unstamped_image(self):
        """`docker inspect` on a missing label prints `<no value>`, which would
        become the image tag and send Compose looking for
        `bonuschef:<no value>`."""
        text = self.WRAPPER.read_text()
        assert "<no value>" in text, "an unstamped image would yield a bogus tag"
        assert "unknown" in text

    def test_the_version_is_not_pushed_into_dot_env(self):
        """The services read .env into their environment, so a version there
        would override the one baked into the image - and the portal would
        report a version it is not running, which is the exact confusion the
        stamp exists to prevent.
        """
        for script in ("compose.sh", "deploy.sh", "build-image.sh"):
            text = (REPO_ROOT / "scripts" / script).read_text()
            for line in text.splitlines():
                if line.strip().startswith("#"):
                    continue
                assert "BONUSCHEF_VERSION" not in line or ".env" not in line, (
                    f"{script} writes the version into .env: {line.strip()!r}"
                )

    def test_no_documented_command_calls_compose_without_a_version(self):
        """A runbook command that fails on the first line is worse than no
        runbook: it is followed during an incident, by someone who then has to
        debug the instructions instead of the fault.
        """
        offenders = []
        for doc in (REPO_ROOT / "docs").rglob("*.md"):
            for number, line in _logical_lines(doc.read_text()):
                stripped = line.strip()
                if "docker compose" not in stripped:
                    continue
                # Inside backticks is prose about the command, not a command.
                if (
                    stripped.startswith(("`", "-", "*"))
                    or "`docker compose" in stripped
                ):
                    continue
                # `docker compose version` parses no file.
                if "docker compose version" in stripped:
                    continue
                # An explicit value supplied inline is fine.
                if "BONUSCHEF_VERSION=" in stripped:
                    continue
                if "./scripts/compose.sh" in stripped:
                    continue
                offenders.append(f"{doc.relative_to(REPO_ROOT)}:{number}: {stripped}")
        assert not offenders, (
            "these would fail on a missing BONUSCHEF_VERSION; route them "
            "through ./scripts/compose.sh:\n  " + "\n  ".join(offenders)
        )

    def test_no_doc_still_tells_anyone_to_build_during_up(self):
        for doc in (REPO_ROOT / "docs").rglob("*.md"):
            for number, line in enumerate(doc.read_text().splitlines(), 1):
                assert "compose up" not in line or "--build" not in line, (
                    f"{doc.name}:{number} rebuilds in place, so what runs is "
                    "not the artifact that was watched"
                )
