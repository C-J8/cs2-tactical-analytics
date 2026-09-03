from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from airflow.sdk import task


PROJECT_ROOT = Path(os.environ.get("CS2_PROJECT_ROOT", "/opt/airflow/project")).resolve()
PROJECT_CONFIG = "configs/project.yaml"


@task(retries=1)
def run_project_module(
    module: str,
    arguments: list[Any] | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Run one existing project CLI as an isolated Airflow task."""
    if not module.startswith("src."):
        raise ValueError(f"Only project modules are allowed, received: {module}")

    command = [sys.executable, "-m", module]
    command.extend(str(value) for value in arguments or [])
    if force:
        command.append("--force")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in [str(PROJECT_ROOT), environment.get("PYTHONPATH", "")] if value
    )

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
    )
    return {"module": module, "status": "completed"}
