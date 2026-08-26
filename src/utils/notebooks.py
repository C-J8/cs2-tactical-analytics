from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils.io import ensure_dir


def md(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": [source]}


def code(source: str) -> dict[str, Any]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": [source]}


def notebook_json(cells: list[dict[str, Any]]) -> str:
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, indent=2)


def write_notebook(path: Path, cells: list[dict[str, Any]], *, force: bool) -> Path:
    if path.exists() and not force:
        return path
    ensure_dir(path.parent)
    path.write_text(notebook_json(cells), encoding="utf-8")
    return path
