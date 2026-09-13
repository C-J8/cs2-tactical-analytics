from __future__ import annotations

import argparse
import hashlib
import io
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pandas as pd

from src.maps.registry import load_map_registry
from src.utils.io import ensure_dir, write_dataframe_outputs


def selected_members(archive: ZipFile, map_name: str) -> list[str]:
    requested = map_name.casefold()
    result = []
    for member in archive.namelist():
        path = PurePosixPath(member)
        if member.endswith("/"):
            continue
        normalized = path.name.casefold()
        if requested in member.casefold() or normalized == "map-data.json":
            result.append(member)
    return result


def safe_relative_path(member: str) -> Path:
    parts = [part for part in PurePosixPath(member).parts if part not in {"", ".", ".."}]
    if not parts:
        raise ValueError(f"Unsafe or empty archive member: {member}")
    return Path(*parts)


def sync_awpy_assets(
    map_name: str,
    *,
    registry_path: Path = Path("configs/maps/map_registry.yaml"),
    project_root: Path = Path("."),
    force: bool = False,
    dry_run: bool = False,
) -> tuple[pd.DataFrame, dict[str, Path]]:
    registry = load_map_registry(map_name, registry_path=registry_path)
    assets = registry.assets
    if assets.get("provider") != "awpy-data":
        raise ValueError(f"Unsupported map asset provider: {assets.get('provider')}")
    client_version = str(assets["client_version"])
    steam_build_id = str(assets["steam_build_id"])
    url_template = str(assets["source_url_template"])
    metadata_url_template = str(assets["metadata_url_template"])
    destination_root = Path(str(assets["project_local_root"]))
    if not destination_root.is_absolute():
        destination_root = project_root / destination_root
    manifest_rows: list[dict[str, object]] = []
    resources = list(assets.get("resources") or [])
    if dry_run:
        for resource in resources:
            manifest_rows.append(
                {
                    "provider": "awpy-data",
                    "client_version": client_version,
                    "steam_build_id": steam_build_id,
                    "map_id": registry.map_id,
                    "resource": resource,
                    "source_url": url_template.format(client_version=client_version, resource=resource),
                    "source_member": None,
                    "local_path": None,
                    "sha256": None,
                    "size_bytes": None,
                    "status": "planned",
                }
            )
        for filename in assets.get("metadata_files", []):
            manifest_rows.append(
                {
                    "provider": "awpy-data",
                    "client_version": client_version,
                    "steam_build_id": steam_build_id,
                    "map_id": registry.map_id,
                    "resource": "metadata",
                    "source_url": metadata_url_template.format(client_version=client_version, filename=filename),
                    "source_member": filename,
                    "local_path": None,
                    "sha256": None,
                    "size_bytes": None,
                    "status": "planned",
                }
            )
        return pd.DataFrame(manifest_rows), {}

    for resource in resources:
        source_url = url_template.format(client_version=client_version, resource=resource)
        payload = download(source_url)
        with ZipFile(io.BytesIO(payload)) as archive:
            members = selected_members(archive, registry.game_map_name)
            if not members:
                raise ValueError(f"No {registry.game_map_name} assets found in {source_url}")
            for member in members:
                body = archive.read(member)
                target = destination_root / resource / safe_relative_path(member)
                ensure_dir(target.parent)
                if force or not target.exists():
                    target.write_bytes(body)
                manifest_rows.append(
                    {
                        "provider": "awpy-data",
                        "client_version": client_version,
                        "steam_build_id": steam_build_id,
                        "map_id": registry.map_id,
                        "resource": resource,
                        "source_url": source_url,
                        "source_member": member,
                        "local_path": target.relative_to(project_root).as_posix(),
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "size_bytes": len(body),
                        "status": "materialized",
                    }
                )
    for filename in assets.get("metadata_files", []):
        source_url = metadata_url_template.format(client_version=client_version, filename=filename)
        body = download(source_url)
        target = destination_root / filename
        ensure_dir(target.parent)
        if force or not target.exists():
            target.write_bytes(body)
        manifest_rows.append(
            {
                "provider": "awpy-data",
                "client_version": client_version,
                "steam_build_id": steam_build_id,
                "map_id": registry.map_id,
                "resource": "metadata",
                "source_url": source_url,
                "source_member": filename,
                "local_path": target.relative_to(project_root).as_posix(),
                "sha256": hashlib.sha256(body).hexdigest(),
                "size_bytes": len(body),
                "status": "materialized",
            }
        )
    manifest = pd.DataFrame(manifest_rows)
    outputs = write_dataframe_outputs(
        {"mirage_asset_manifest": manifest},
        destination_root,
        force=force,
        formats=("csv", "parquet"),
    )
    return manifest, outputs


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "cs2-tactical-analytics-map-assets/1.0"})
    with urlopen(request, timeout=120) as response:  # noqa: S310 - URL is version-pinned in project config
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize version-pinned Awpy assets for one registered map.")
    parser.add_argument("--map", default="Mirage")
    parser.add_argument("--registry", type=Path, default=Path("configs/maps/map_registry.yaml"))
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifest, outputs = sync_awpy_assets(
        args.map,
        registry_path=args.registry,
        project_root=args.project_root.resolve(),
        force=args.force,
        dry_run=args.dry_run,
    )
    print(
        {
            "map": args.map,
            "assets": len(manifest),
            "statuses": manifest["status"].value_counts().to_dict(),
            "outputs": {key: str(value) for key, value in outputs.items()},
        }
    )


if __name__ == "__main__":
    main()
