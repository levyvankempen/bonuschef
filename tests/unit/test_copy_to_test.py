"""Copying production's data into the test environment.

The script runs `DROP SCHEMA ... CASCADE` and `pg_restore` against whatever it
is pointed at, so the interesting tests are the refusals rather than the happy
path. Being pointed at production once is the whole catastrophe.

Exercised end to end against a stub `docker` on PATH: no database, no network,
no containers. What that proves is the script's own logic - its guards, the
order it does things in, and the retention arithmetic - which is all of it that
can be wrong in a way worth catching here.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "copy-to-test.sh"


def _code(path: Path) -> str:
    """The script with its comments removed.

    Ordering assertions must read the commands, not the prose about them. The
    comments here quote the `pg_restore` failure and name `DROP SCHEMA` and
    `pg_dump` while explaining why the portal is stopped first, so a plain
    `text.index(...)` finds the explanation and asserts something about a
    sentence.
    """
    return "\n".join(
        line
        for line in path.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )


# A stub that answers every docker call this script makes. The transcript it
# writes is what the ordering tests read.
STUB = r"""#!/usr/bin/env bash
echo "$*" >> "$TRANSCRIPT"
case "$1 $2" in
  "ps -q")
    case "$*" in
      *bonuschef-test*) echo testdb ;;
      *streamlit*)      echo prodweb ;;
      *)                [ "${NO_PROD_DB:-0}" = 1 ] || echo proddb ;;
    esac
    ;;
  "inspect "*|"inspect")
    echo "v1.40.2" ;;
  "compose "*|"compose")
    ;;
  "exec "*|"exec")
    # The command is the first argument that is not a flag or a container id.
    for arg in "$@"; do
      case "$arg" in
        pg_dump)   printf '%s' "${DUMP_BODY-PGDMP-fake-dump}" ; exit 0 ;;
        pg_restore) cat > /dev/null ; exit 0 ;;
        psql)      cat > /dev/null ; exit 0 ;;
        pg_isready) exit 0 ;;
        date)      echo "20260110T120000Z" ; exit 0 ;;
        du)        echo "1.1G	x" ; exit 0 ;;
      esac
    done
    ;;
esac
exit 0
"""


@pytest.fixture
def workspace(tmp_path: Path):
    """A scratch copy of the script with a stub docker in front of it."""
    (tmp_path / "scripts").mkdir()
    target = tmp_path / "scripts" / "copy-to-test.sh"
    target.write_bytes(SCRIPT.read_bytes())
    target.chmod(0o755)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "docker"
    stub.write_text(STUB)
    stub.chmod(0o755)

    data = tmp_path / "ssd"
    data.mkdir()
    (tmp_path / ".env.test").write_text(
        f"BONUSCHEF_TEST_DATA_DIR={data}\nPOSTGRES_PASSWORD=x\n"
    )
    return tmp_path


def run(workspace: Path, **env) -> subprocess.CompletedProcess:
    transcript = workspace / "transcript"
    transcript.touch()
    environment = {
        **os.environ,
        "PATH": f"{workspace / 'bin'}:{os.environ['PATH']}",
        "TRANSCRIPT": str(transcript),
        **env,
    }
    return subprocess.run(
        ["bash", str(workspace / "scripts" / "copy-to-test.sh")],
        cwd=workspace,
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )


def transcript(workspace: Path) -> list[str]:
    path = workspace / "transcript"
    return path.read_text().splitlines() if path.exists() else []


# --- the refusals -----------------------------------------------------------


class TestItRefusesToTouchProduction:
    def test_it_refuses_when_the_target_is_the_production_project(self, workspace):
        result = run(workspace, BONUSCHEF_TEST_PROJECT="bonuschef")
        assert result.returncode != 0
        assert "production" in result.stderr.lower()
        assert not any("pg_restore" in line for line in transcript(workspace))

    def test_it_refuses_a_target_not_named_as_a_test_environment(self, workspace):
        """Belt and braces, and the braces matter: `BONUSCHEF_TEST_PROJECT`
        pointing at some third project would pass the inequality check and
        still not be a test environment."""
        result = run(workspace, BONUSCHEF_TEST_PROJECT="bonuschef-staging-2")
        assert result.returncode != 0
        assert "not named as a test environment" in result.stderr
        assert not any("pg_restore" in line for line in transcript(workspace))

    def test_the_guard_is_on_the_project_not_on_a_host_or_port(self):
        """A host and a port are variables that get edited. The project name is
        what Docker uses to decide which containers these are, so it cannot
        disagree with reality."""
        text = SCRIPT.read_text()
        guard = text[text.index("The guard that matters") : text.index("container_for")]
        assert "TEST_PROJECT" in guard and "PROD_PROJECT" in guard
        assert "PG_HOST" not in guard and "PG_PORT" not in guard

    def test_it_addresses_containers_by_label_not_by_name(self):
        """The container names are derived from the project now, precisely so
        two stacks can coexist - which means guessing a name is how you address
        the wrong stack."""
        text = SCRIPT.read_text()
        assert "com.docker.compose.project" in text
        assert "com.docker.compose.service" in text
        for guessed in ("pg_bonuschef", "streamlit_portal"):
            assert guessed not in text


class TestItRefusesWhenItCannotDoTheJob:
    def test_no_env_file_is_a_refusal(self, workspace):
        (workspace / ".env.test").unlink()
        result = run(workspace)
        assert result.returncode != 0
        assert ".env.test" in result.stderr

    def test_an_unset_data_directory_is_a_refusal(self, workspace):
        (workspace / ".env.test").write_text("POSTGRES_PASSWORD=x\n")
        result = run(workspace)
        assert result.returncode != 0
        assert "BONUSCHEF_TEST_DATA_DIR" in result.stderr

    def test_production_not_running_is_a_refusal(self, workspace):
        result = run(workspace, NO_PROD_DB="1")
        assert result.returncode != 0
        assert "not running" in result.stderr
        assert not any("pg_restore" in line for line in transcript(workspace))

    def test_an_empty_dump_is_not_restored(self, workspace):
        """The dangerous failure. A dump that came back empty - production
        down, a disk full, pg_dump refusing - restored over the test database
        would wipe it and report success.
        """
        result = run(workspace, DUMP_BODY="")
        assert result.returncode != 0
        assert "empty" in result.stderr
        assert not any("pg_restore" in line for line in transcript(workspace))


# --- what it does when it does run ------------------------------------------


class TestTheCopyItself:
    def test_it_succeeds_against_the_stub(self, workspace):
        result = run(workspace)
        assert result.returncode == 0, result.stderr

    def test_production_is_only_read_from(self, workspace):
        """One way, always. The requirement says data moves from production to
        the test environment and never the other way."""
        run(workspace)
        for line in transcript(workspace):
            if "proddb" not in line:
                continue
            for mutation in ("pg_restore", "DROP", "psql -U postgres -d postgres -v"):
                assert mutation not in line, f"production was written to: {line}"

    def test_the_dump_is_taken_before_the_schema_is_dropped(self, workspace):
        """Order is the whole safety property. Dropping first and then finding
        the dump failed leaves the test environment with nothing."""
        run(workspace)
        lines = transcript(workspace)
        dumped = next(i for i, line in enumerate(lines) if "pg_dump" in line)
        restored = next(i for i, line in enumerate(lines) if "pg_restore" in line)
        assert dumped < restored

    def test_the_dump_is_kept_on_the_configured_disk(self, workspace):
        run(workspace)
        dumps = list((workspace / "ssd" / "dumps").glob("production-*.dump"))
        assert dumps, "no dump file was kept, so the copy is not repeatable"

    def test_it_drops_the_schema_rather_than_restoring_over_live_tables(self):
        """`pg_restore --clean` alone leaves anything the dump does not mention
        - a table from a version since rolled back, say - which is how a test
        environment comes to hold rows that exist nowhere else."""
        text = SCRIPT.read_text()
        assert "DROP SCHEMA IF EXISTS public CASCADE" in text
        assert "DROP SCHEMA IF EXISTS public_marts CASCADE" in text
        assert text.index("DROP SCHEMA") < text.index("pg_restore -U postgres")

    def test_it_records_when_the_copy_was_taken(self):
        text = SCRIPT.read_text()
        assert "public.environment_copy" in text
        assert "copied_at" in text

    def test_the_timestamp_is_the_copys_not_the_datas(self):
        """`now()` at restore time. Reading the newest row of some data table
        instead would conflate "this copy is a week old" with "production's
        pipeline was down when I copied"."""
        text = SCRIPT.read_text()
        insert = text[text.index("INSERT INTO public.environment_copy") :]
        insert = insert[: insert.index("PSQL")]
        assert "now()" in insert
        assert "max(" not in insert.lower()

    def test_it_records_which_version_produced_the_copy(self):
        """So a defect found in the copy can be matched to the code that wrote
        the rows."""
        assert "org.opencontainers.image.version" in SCRIPT.read_text()

    def test_writing_the_stamp_is_upsert_so_a_second_copy_works(self):
        text = SCRIPT.read_text()
        assert "ON CONFLICT (only_row) DO UPDATE" in text


class TestItTakesTheApplicationOffTheDatabaseFirst:
    """You cannot restore a database underneath a running application, and this
    one writes SCHEMA rather than just rows.

    Observed on the first real copy against production. The restore takes about
    a minute, the drop had already run, and the portal's health probe - every
    30 seconds - recreated the account tables in the middle of it:

        pg_restore: error: could not execute query: ERROR:
        relation "account_sessions_account_idx" already exists

    The portal applies `ensure_account_tables` from its cached engine, so any
    render or probe during the window is enough.
    """

    def test_the_portal_is_stopped_before_the_schema_is_dropped(self):
        text = _code(SCRIPT)
        assert text.index("compose_test stop streamlit") < text.index("DROP SCHEMA"), (
            "the portal is still serving when the schema is dropped, so it can "
            "recreate tables mid-restore"
        )

    def test_it_is_stopped_before_the_dump_is_even_taken(self):
        """Simplest correct window: closed for the whole operation rather than
        only around the restore."""
        text = _code(SCRIPT)
        assert text.index("compose_test stop streamlit") < text.index("pg_dump")

    def test_only_the_portal_is_stopped_not_its_database(self):
        """The database is what is being restored INTO; stopping it would make
        the restore impossible."""
        text = SCRIPT.read_text()
        stops = [
            line
            for line in text.splitlines()
            if "compose_test stop" in line and not line.lstrip().startswith("#")
        ]
        assert stops, "nothing is stopped"
        for line in stops:
            assert "postgres" not in line, f"it stops its own database: {line.strip()}"

    def test_a_failed_restore_still_brings_the_portal_back(self):
        """The point of the test environment is being there when somebody wants
        to look. A failed copy that also leaves it down turns one problem into
        two."""
        text = SCRIPT.read_text()
        assert "trap restart_app EXIT" in text

    def test_the_trap_is_cleared_before_the_deliberate_restart(self):
        """Otherwise the restart runs twice - harmless, but it means the exit
        path and the success path disagree about who owns the restart."""
        text = _code(SCRIPT)
        assert text.index("trap - EXIT") < text.rindex("restart_app")

    def test_the_portal_is_running_again_when_it_finishes(self, workspace):
        """Exercised, not just read: the stub records compose calls."""
        result = run(workspace)
        assert result.returncode == 0, result.stderr
        calls = [c for c in transcript(workspace) if "compose" in c]
        stopped = [i for i, c in enumerate(calls) if "stop streamlit" in c]
        started = [i for i, c in enumerate(calls) if "start streamlit" in c]
        assert stopped, f"never stopped the portal: {calls}"
        assert started, f"never restarted the portal: {calls}"
        assert stopped[0] < started[-1], "restarted before it stopped"


# --- bounded growth ---------------------------------------------------------


class TestTheDumpsDoNotFillTheDisk:
    def _existing(self, workspace: Path) -> list[str]:
        return sorted(p.name for p in (workspace / "ssd" / "dumps").glob("*.dump"))

    @pytest.fixture
    def with_old_dumps(self, workspace: Path):
        dumps = workspace / "ssd" / "dumps"
        dumps.mkdir(parents=True)
        # Oldest first, so mtime order is unambiguous.
        for index in range(1, 6):
            path = dumps / f"production-2026010{index}T000000Z.dump"
            path.write_text("old")
            os.utime(path, (index * 1000, index * 1000))
        return workspace

    def test_it_keeps_the_most_recent_and_deletes_the_rest(self, with_old_dumps):
        result = run(with_old_dumps, BONUSCHEF_KEEP_DUMPS="3")
        assert result.returncode == 0, result.stderr
        remaining = self._existing(with_old_dumps)
        assert len(remaining) == 3, remaining
        # The new one plus the two newest old ones; the three oldest are gone.
        assert "production-20260101T000000Z.dump" not in remaining
        assert "production-20260105T000000Z.dump" in remaining

    def test_the_retention_count_is_configurable(self, with_old_dumps):
        result = run(with_old_dumps, BONUSCHEF_KEEP_DUMPS="1")
        assert result.returncode == 0, result.stderr
        assert len(self._existing(with_old_dumps)) == 1

    def test_a_deletion_is_announced(self, with_old_dumps):
        """A deletion nobody mentioned is one nobody can question."""
        result = run(with_old_dumps, BONUSCHEF_KEEP_DUMPS="2")
        assert "removing old dump" in result.stderr

    def test_it_does_not_delete_anything_it_did_not_create(self, with_old_dumps):
        unrelated = with_old_dumps / "ssd" / "dumps" / "keep-me.sql.gz"
        unrelated.write_text("someone else's backup")
        run(with_old_dumps, BONUSCHEF_KEEP_DUMPS="1")
        assert unrelated.exists(), "it deleted a file outside its own naming"
