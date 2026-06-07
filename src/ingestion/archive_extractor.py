from __future__ import annotations

import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.ingestion.demo_downloader import sha256_file
from src.utils.io import ensure_dir
from src.utils.text import safe_slug


@dataclass
class ExtractedDemo:
    status: str
    path: Path | None
    file_size_bytes: int | None
    sha256: str | None
    extracted_at: str | None
    error_message: str | None = None
    original_file_name: str | None = None
    is_merged: bool = False
    split_group_id: str | None = None
    split_part_number: int | None = None


@dataclass
class ExtractionResult:
    status: str
    demos: list[ExtractedDemo]
    error_message: str | None = None


def detect_archive_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".dem":
        return "dem"
    if suffix == ".zip":
        return "zip"
    if suffix == ".rar":
        return "rar"
    if suffix == ".7z":
        return "7z"
    return "unknown"


class ArchiveExtractor:
    def extract(self, archive_path: Path, output_dir: Path, base_name: str, *, force: bool = False) -> ExtractionResult:
        ensure_dir(output_dir)
        if force:
            clear_existing_dems(output_dir)
        archive_type = detect_archive_type(archive_path)
        if archive_type == "dem":
            return self._handle_dem(archive_path, output_dir, base_name, force=force)
        if archive_type == "zip":
            return self._extract_zip(archive_path, output_dir, base_name, force=force)
        if archive_type == "rar":
            return self._extract_rar(archive_path, output_dir, base_name, force=force)
        return ExtractionResult("unsupported_archive", [], f"Unsupported archive type: {archive_path.suffix}")

    def _handle_dem(self, archive_path: Path, output_dir: Path, base_name: str, *, force: bool) -> ExtractionResult:
        output_path = output_dir / f"{base_name}.dem"
        if output_path.exists() and not force:
            return ExtractionResult("skipped_existing", [self._demo_result("skipped_existing", output_path)])
        if archive_path.resolve() != output_path.resolve():
            shutil.copy2(archive_path, output_path)
        return ExtractionResult("not_needed", [self._demo_result("not_needed", output_path, original_file_name=archive_path.name)])

    def _extract_zip(self, archive_path: Path, output_dir: Path, base_name: str, *, force: bool) -> ExtractionResult:
        demos: list[ExtractedDemo] = []
        try:
            with zipfile.ZipFile(archive_path) as archive:
                dem_members = [member for member in archive.namelist() if member.lower().endswith(".dem")]
                if not dem_members:
                    return ExtractionResult("failed", [], "No .dem files found inside zip archive")
                for member in dem_members:
                    output_path = output_dir / f"{base_name}_{safe_slug(Path(member).stem)}.dem"
                    if output_path.exists() and not force:
                        demos.append(self._demo_result("skipped_existing", output_path, original_file_name=Path(member).name))
                        continue
                    with archive.open(member) as source, output_path.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    demos.append(self._demo_result("extracted", output_path, original_file_name=Path(member).name))
        except (zipfile.BadZipFile, OSError) as exc:
            return ExtractionResult("failed", [], str(exc))

        if demos and all(demo.status == "skipped_existing" for demo in demos):
            return ExtractionResult("skipped_existing", demos)
        return ExtractionResult("extracted", demos)

    def _extract_rar(self, archive_path: Path, output_dir: Path, base_name: str, *, force: bool) -> ExtractionResult:
        seven_zip = find_7zip()
        if not seven_zip:
            return ExtractionResult("unsupported_archive", [], "RAR extraction requires 7z/7za on PATH")

        before = {path.resolve() for path in output_dir.rglob("*.dem")}
        command = [seven_zip, "x", "-y" if force else "-aos", f"-o{output_dir}", str(archive_path)]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            return ExtractionResult("failed", [], str(exc))
        if completed.returncode != 0:
            return ExtractionResult("failed", [], completed.stderr.strip() or completed.stdout.strip())

        after_paths = sorted(
            [path for path in output_dir.rglob("*.dem") if path.resolve() not in before or force],
            key=lambda path: path.name.lower(),
        )
        demos = []
        for path in after_paths:
            original_file_name = path.name
            target = output_dir / f"{base_name}_{safe_slug(path.stem)}.dem"
            if path != target:
                if target.exists() and not force:
                    demos.append(self._demo_result("skipped_existing", target, original_file_name=original_file_name))
                    continue
                path.replace(target)
            demos.append(self._demo_result("extracted", target, original_file_name=original_file_name))

        if not demos:
            return ExtractionResult("failed", [], "No .dem files found after RAR extraction")
        return ExtractionResult("extracted", demos)

    def _demo_result(self, status: str, path: Path, *, original_file_name: str | None = None) -> ExtractedDemo:
        return ExtractedDemo(
            status=status,
            path=path,
            file_size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
            extracted_at=datetime.now(timezone.utc).isoformat() if status in {"extracted", "not_needed"} else None,
            original_file_name=original_file_name,
        )


def build_demo_base_name(row: dict[str, object]) -> str:
    series_id = safe_slug(row.get("series_id") or row.get("hltv_match_id"), fallback="unknown_series")
    map_name = safe_slug(row.get("map_name"), fallback="unknown_map")
    map_number = safe_slug(row.get("map_number"), fallback="x")
    return f"{series_id}_{map_name}_map{map_number}"


def find_7zip() -> str | None:
    executable = shutil.which("7z") or shutil.which("7za")
    if executable:
        return executable
    for path in [Path("C:/Program Files/7-Zip/7z.exe"), Path("C:/Program Files (x86)/7-Zip/7z.exe")]:
        if path.exists():
            return str(path)
    return None


def clear_existing_dems(output_dir: Path) -> None:
    for path in output_dir.rglob("*.dem"):
        path.unlink()
