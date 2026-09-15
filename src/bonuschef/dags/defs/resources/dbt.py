"""Definition of dbt resources."""

import shutil
import sys
from pathlib import Path

from dagster_dbt import DbtCliResource

from bonuschef.dags.defs.assets.dbt.dbt_project import project


def _dbt_executable() -> str:
    """Find dbt without relying on PATH.

    DbtCliResource defaults to the bare name "dbt" and resolves it through
    PATH. That held only while the containers started through `uv run`, which
    prepends the venv's bin directory; calling the venv binaries directly to
    save ~180MB per container removed it, and every Dagster code location then
    failed to load with "The dbt executable 'dbt' does not exist".

    dbt is installed beside the interpreter that is running us, so ask there
    first and fall back to PATH for a developer shell that has it elsewhere.
    """
    beside_interpreter = Path(sys.executable).parent / "dbt"
    if beside_interpreter.exists():
        return str(beside_interpreter)
    return shutil.which("dbt") or "dbt"


dbt = DbtCliResource(project_dir=project, dbt_executable=_dbt_executable())
