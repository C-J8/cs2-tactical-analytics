from __future__ import annotations

import ast
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


REPO = Path(r"E:\Projeto CS")
OUT = Path(r"C:\Users\celso\OneDrive\Documentos\ChatGPT\Projeto CS\.codex-build")
SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def short_doc(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.strip().split())[:500]


def category(path: Path) -> str:
    rel = path.relative_to(REPO)
    first = rel.parts[0] if rel.parts else "root"
    if first == "data":
        return "data"
    if first == "src":
        return "source"
    if first == "tests":
        return "test"
    if first == "notebooks":
        return "notebook"
    if first == "docs":
        return "documentation"
    if first == "configs":
        return "configuration"
    if first == "dags":
        return "orchestration"
    if first == "docker":
        return "container"
    if first == ".github":
        return "ci"
    if first == "scripts":
        return "script"
    return "root"


def inspect_python(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        return {"parse_error": str(exc)}
    defs = []
    classes = []
    imports = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_") or node.name == "__main__":
                defs.append({"name": node.name, "line": node.lineno, "doc": short_doc(ast.get_docstring(node))})
        elif isinstance(node, ast.ClassDef):
            classes.append({"name": node.name, "line": node.lineno, "doc": short_doc(ast.get_docstring(node))})
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "src" or node.module.startswith("src.") or node.module.startswith("dags.")):
                imports.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src" or alias.name.startswith("src.") or alias.name.startswith("dags."):
                    imports.append(alias.name)
    return {
        "module_doc": short_doc(ast.get_docstring(tree)),
        "functions": defs,
        "classes": classes,
        "internal_imports": sorted(set(imports)),
        "has_main": 'if __name__ == "__main__"' in source or "if __name__ == '__main__'" in source,
        "lines": source.count("\n") + 1,
    }


def inspect_notebook(path: Path) -> dict:
    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"parse_error": str(exc)}
    headings = []
    code_cells = 0
    markdown_cells = 0
    for cell in nb.get("cells", []):
        source = "".join(cell.get("source", []))
        if cell.get("cell_type") == "code":
            code_cells += 1
        elif cell.get("cell_type") == "markdown":
            markdown_cells += 1
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    headings.append(stripped[:240])
    return {
        "title": headings[0].lstrip("# ") if headings else path.stem,
        "headings": headings[:30],
        "code_cells": code_cells,
        "markdown_cells": markdown_cells,
    }


def inspect_markdown(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"parse_error": str(exc)}
    headings = [line.strip() for line in text.splitlines() if line.lstrip().startswith("#")]
    return {
        "title": headings[0].lstrip("# ") if headings else path.stem,
        "headings": headings[:50],
        "lines": text.count("\n") + 1,
    }


def inspect_text_config(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"parse_error": str(exc)}
    keys = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        if ":" in stripped:
            key = stripped.split(":", 1)[0].strip().strip('"\'')
            if key and " " not in key and key not in keys:
                keys.append(key)
        elif "=" in stripped and not stripped.startswith("http"):
            key = stripped.split("=", 1)[0].strip()
            if key and key not in keys:
                keys.append(key)
    return {"top_keys": keys[:80], "lines": text.count("\n") + 1}


def main() -> None:
    rows = []
    for path in sorted(REPO.rglob("*")):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
            continue
        rel = path.relative_to(REPO).as_posix()
        suffix = path.suffix.lower()
        detail: dict = {}
        if suffix == ".py":
            detail = inspect_python(path)
        elif suffix == ".ipynb":
            detail = inspect_notebook(path)
        elif suffix == ".md":
            detail = inspect_markdown(path)
        elif suffix in {".yaml", ".yml", ".toml", ".txt", ".example", ".gitignore", ".dockerignore", ".gitattributes"} or path.name.startswith("Dockerfile"):
            detail = inspect_text_config(path)
        rows.append({
            "path": rel,
            "bytes": path.stat().st_size,
            "extension": suffix or path.name,
            "category": category(path),
            "detail": detail,
        })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "repo_inventory.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "repo_inventory.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "bytes", "extension", "category", "summary"])
        writer.writeheader()
        for row in rows:
            d = row["detail"]
            summary = d.get("module_doc") or d.get("title") or ", ".join(d.get("top_keys", [])[:12])
            writer.writerow({**{k: row[k] for k in ["path", "bytes", "extension", "category"]}, "summary": summary})

    by_category = Counter(row["category"] for row in rows)
    by_extension = Counter(row["extension"] for row in rows)
    data_prefixes: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    for row in rows:
        if row["category"] != "data":
            continue
        parts = row["path"].split("/")
        key = "/".join(parts[:4]) if len(parts) >= 4 else "/".join(parts[:-1])
        data_prefixes[key]["files"] += 1
        data_prefixes[key]["bytes"] += row["bytes"]
    summary = {
        "total_files": len(rows),
        "total_bytes": sum(row["bytes"] for row in rows),
        "by_category": dict(by_category),
        "by_extension": dict(by_extension),
        "data_prefixes": dict(sorted(data_prefixes.items())),
    }
    (OUT / "repo_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
