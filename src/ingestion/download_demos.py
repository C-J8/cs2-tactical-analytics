from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from src.config.schemas import ProjectConfig, load_project_config
from src.ingestion.archive_extractor import ArchiveExtractor, build_demo_base_name, detect_archive_type
from src.ingestion.demo_downloader import DemoDownloader, DownloadResult, sha256_file
from src.ingestion.hltv_client import HltvClient, parse_match_page
from src.utils.io import default_catalog_path, ensure_dir, read_catalog, write_manifest
from src.utils.logging import configure_logging
from src.utils.text import clean_string, safe_slug

MANIFEST_COLUMNS = [
    "demo_record_id",
    "series_id",
    "hltv_match_id",
    "match_url",
    "match_date",
    "event_name",
    "target_team",
    "opponent",
    "map_name",
    "map_number",
    "demo_link",
    "archive_url",
    "archive_path",
    "archive_file_name",
    "archive_file_size_bytes",
    "archive_sha256",
    "dem_path",
    "dem_file_name",
    "dem_file_size_bytes",
    "dem_sha256",
    "download_status",
    "extract_status",
    "status",
    "error_message",
    "downloaded_at",
    "extracted_at",
]

LOCAL_ARCHIVE_EXTENSIONS = [".dem", ".zip", ".rar", ".download"]


def run_download_pipeline(
    config_path: Path,
    *,
    catalog_path: Path | None = None,
    include_warnings: bool = False,
    dry_run: bool = False,
    limit: int | None = None,
    force: bool | None = None,
    no_extract: bool = False,
    local_only: bool = False,
    archive_path: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    if archive_path is not None and not archive_path.exists():
        raise FileNotFoundError(f"Local archive not found: {archive_path}")
    catalog_path = catalog_path or default_catalog_path(project.silver_output_dir)
    catalog = read_catalog(catalog_path)
    total_read = len(catalog)
    eligible = select_eligible_rows(catalog, include_warnings=include_warnings)

    run_limit = limit if limit is not None else project.max_downloads_per_run
    if run_limit is not None:
        eligible = eligible.head(run_limit)

    manifest_rows = process_rows(
        eligible,
        project,
        dry_run=dry_run,
        force=project.force_download if force is None else force,
        extract=project.extract_archives and not no_extract,
        local_only=local_only,
        archive_path=archive_path,
    )
    manifest = pd.DataFrame(manifest_rows, columns=MANIFEST_COLUMNS)
    outputs = write_manifest(manifest, project.demo_manifest_dir, project.output_formats)
    summary = build_summary(total_read, len(eligible), manifest)
    return manifest, outputs, summary


def select_eligible_rows(catalog: pd.DataFrame, *, include_warnings: bool = False) -> pd.DataFrame:
    if include_warnings:
        return catalog[catalog["validation_status"].isin(["ok", "warning"])].copy()
    return catalog[catalog["validation_status"] == "ok"].copy()


def process_rows(
    rows: pd.DataFrame,
    project: ProjectConfig,
    *,
    dry_run: bool,
    force: bool,
    extract: bool,
    local_only: bool = False,
    archive_path: Path | None = None,
) -> list[dict[str, object]]:
    extractor = ArchiveExtractor()
    manifest_rows: list[dict[str, object]] = []
    downloader: DemoDownloader | None = None
    hltv_client: HltvClient | None = None

    for _, row in rows.iterrows():
        row_dict = row.to_dict()
        demo_link = clean_string(row_dict.get("demo_link"))

        if dry_run and not demo_link and not local_only and archive_path is None:
            manifest_rows.append(base_manifest_row(row_dict, download_status="missing_demo_link", extract_status="not_needed", status="warning", error_message="demo_link is missing"))
            continue

        demo_output_dir = build_demo_output_dir(project.demo_output_dir, row_dict)

        if dry_run:
            planned_archive_path = build_archive_path(project.demo_archive_dir, row_dict, demo_link or "")
            manifest_rows.append(
                base_manifest_row(
                    row_dict,
                    archive_url=demo_link,
                    archive_path=planned_archive_path,
                    download_status="dry_run",
                    extract_status="dry_run",
                    status="warning",
                    error_message="dry run: no files downloaded or extracted",
                )
            )
            continue

        if archive_path is not None:
            manifest_rows.extend(process_explicit_archive(row_dict, archive_path, project, extractor, demo_output_dir, extract=extract, force=force))
            continue

        if local_only:
            manifest_rows.extend(process_local_archive(row_dict, project, extractor, demo_output_dir, extract=extract, force=force))
            continue

        if not demo_link and project.mode == "scrape":
            if hltv_client is None:
                hltv_client = HltvClient(
                    project.hltv_cache_dir,
                    cache_enabled=project.cache_enabled,
                    rate_limit_seconds=project.rate_limit_seconds,
                )
            demo_link = try_enrich_demo_link(row_dict, hltv_client)
            row_dict["demo_link"] = demo_link

        if not demo_link:
            manifest_rows.append(base_manifest_row(row_dict, download_status="missing_demo_link", extract_status="not_needed", status="warning", error_message="demo_link is missing"))
            continue

        planned_archive_path = build_archive_path(project.demo_archive_dir, row_dict, demo_link)
        if downloader is None:
            downloader = DemoDownloader(timeout_seconds=project.download_timeout_seconds)
        match_url = clean_string(row_dict.get("match_url"))
        downloader.prime_match_page(match_url)
        download_result = downloader.download(demo_link, planned_archive_path, force=force, referer=match_url)
        if download_result.status in {"failed", "blocked_remote"}:
            failed_archive_path = download_result.path or planned_archive_path
            status = "warning" if download_result.status == "blocked_remote" else "failed"
            manifest_rows.append(row_from_download(row_dict, demo_link, failed_archive_path, download_result, "not_needed", status, download_result.error_message))
            continue

        actual_archive_path = download_result.path or planned_archive_path
        archive_type = detect_archive_type(actual_archive_path)
        extract_rows = build_extract_rows(
            row_dict,
            demo_link,
            actual_archive_path,
            download_result,
            extractor,
            demo_output_dir,
            extract=extract,
            force=force,
            archive_type=archive_type,
        )
        manifest_rows.extend(extract_rows)

        if project.download_rate_limit_seconds > 0:
            time.sleep(project.download_rate_limit_seconds)

    return manifest_rows


def process_local_archive(
    row: dict[str, object],
    project: ProjectConfig,
    extractor: ArchiveExtractor,
    demo_output_dir: Path,
    *,
    extract: bool,
    force: bool,
) -> list[dict[str, object]]:
    local_archive = find_local_archive(project.demo_archive_dir, row)
    if local_archive is None:
        expected = [str(path) for path in expected_local_archive_paths(project.demo_archive_dir, row)]
        return [
            base_manifest_row(
                row,
                archive_path=expected_local_archive_paths(project.demo_archive_dir, row)[-1],
                download_status="missing_local_archive",
                extract_status="not_needed",
                status="warning",
                error_message=f"Local archive not found for base name {build_demo_base_name(row)}. Expected one of: {', '.join(expected)}",
            )
        ]
    download_result = local_download_result("local_existing", local_archive)
    return build_extract_rows(
        row,
        clean_string(row.get("demo_link")) or "",
        local_archive,
        download_result,
        extractor,
        demo_output_dir,
        extract=extract,
        force=force,
        archive_type=detect_archive_type(local_archive),
    )


def process_explicit_archive(
    row: dict[str, object],
    source_archive_path: Path,
    project: ProjectConfig,
    extractor: ArchiveExtractor,
    demo_output_dir: Path,
    *,
    extract: bool,
    force: bool,
) -> list[dict[str, object]]:
    target_archive_path = expected_archive_path(project.demo_archive_dir, row, source_archive_path.suffix.lower())
    ensure_dir(target_archive_path.parent)
    if source_archive_path.resolve() != target_archive_path.resolve() and (force or not target_archive_path.exists()):
        shutil.copy2(source_archive_path, target_archive_path)
    download_result = local_download_result("local_registered", target_archive_path)
    return build_extract_rows(
        row,
        clean_string(row.get("demo_link")) or "",
        target_archive_path,
        download_result,
        extractor,
        demo_output_dir,
        extract=extract,
        force=force,
        archive_type=detect_archive_type(target_archive_path),
    )


def local_download_result(status: str, archive_path: Path) -> DownloadResult:
    return DownloadResult(
        status=status,
        path=archive_path,
        file_size_bytes=archive_path.stat().st_size,
        sha256=sha256_file(archive_path),
        downloaded_at=None,
    )


def build_extract_rows(
    row: dict[str, object],
    demo_link: str,
    archive_path: Path,
    download_result: DownloadResult,
    extractor: ArchiveExtractor,
    demo_output_dir: Path,
    *,
    extract: bool,
    force: bool,
    archive_type: str,
) -> list[dict[str, object]]:
    if not extract:
        return [row_from_download(row, demo_link, archive_path, download_result, "not_needed", "ok", None)]

    extraction = extractor.extract(archive_path, demo_output_dir, build_demo_base_name(row), force=force)
    if not extraction.demos:
        status = "warning" if extraction.status == "unsupported_archive" else "failed"
        return [row_from_download(row, demo_link, archive_path, download_result, extraction.status, status, extraction.error_message)]

    manifest_rows = []
    for demo in extraction.demos:
        status = "ok" if demo.status in {"extracted", "skipped_existing", "not_needed"} else "failed"
        if archive_type == "rar" and extraction.status == "unsupported_archive":
            status = "warning"
        manifest_rows.append(
            row_from_download(
                row,
                demo_link,
                archive_path,
                download_result,
                demo.status,
                status,
                demo.error_message,
                dem_path=demo.path,
                dem_file_size_bytes=demo.file_size_bytes,
                dem_sha256=demo.sha256,
                extracted_at=demo.extracted_at,
            )
        )
    return manifest_rows


def try_enrich_demo_link(row: dict[str, object], hltv_client: HltvClient) -> str | None:
    match_url = clean_string(row.get("match_url"))
    if not match_url:
        return None
    fetch_result = hltv_client.fetch_match_page(match_url, clean_string(row.get("hltv_match_id")))
    if not fetch_result.html:
        return None
    parsed = parse_match_page(fetch_result.html)
    return clean_string(parsed.get("demo_link"))


def build_archive_path(base_dir: Path, row: dict[str, object], demo_link: str) -> Path:
    target_team = safe_folder_name(row.get("target_team"), fallback="unknown_team")
    map_name = safe_folder_name(row.get("map_name"), fallback="unknown_map")
    extension = archive_extension(demo_link)
    return base_dir / target_team / map_name / f"{build_demo_base_name(row)}{extension}"


def expected_archive_path(base_dir: Path, row: dict[str, object], extension: str) -> Path:
    target_team = safe_folder_name(row.get("target_team"), fallback="unknown_team")
    map_name = safe_folder_name(row.get("map_name"), fallback="unknown_map")
    extension = extension if extension.startswith(".") else f".{extension}"
    return base_dir / target_team / map_name / f"{build_demo_base_name(row)}{extension.lower()}"


def expected_local_archive_paths(base_dir: Path, row: dict[str, object]) -> list[Path]:
    return [expected_archive_path(base_dir, row, extension) for extension in LOCAL_ARCHIVE_EXTENSIONS]


def find_local_archive(base_dir: Path, row: dict[str, object]) -> Path | None:
    for path in expected_local_archive_paths(base_dir, row):
        if path.exists():
            return path
    return None


def build_demo_output_dir(base_dir: Path, row: dict[str, object]) -> Path:
    target_team = safe_folder_name(row.get("target_team"), fallback="unknown_team")
    map_name = safe_folder_name(row.get("map_name"), fallback="unknown_map")
    return ensure_dir(base_dir / target_team / map_name)


def safe_folder_name(value: object, *, fallback: str) -> str:
    text = clean_string(value)
    if not text:
        return fallback
    for char in '<>:"/\\|?*':
        text = text.replace(char, "_")
    return text.strip(" .") or fallback


def archive_extension(demo_link: str) -> str:
    suffix = Path(urlparse(demo_link).path).suffix.lower()
    if suffix in {".rar", ".zip", ".dem", ".7z"}:
        return suffix
    return ".download"


def base_manifest_row(
    row: dict[str, object],
    *,
    archive_url: str | None = None,
    archive_path: Path | None = None,
    download_status: str,
    extract_status: str,
    status: str,
    error_message: str | None,
    archive_file_size_bytes: int | None = None,
    archive_sha256: str | None = None,
    dem_path: Path | None = None,
    dem_file_size_bytes: int | None = None,
    dem_sha256: str | None = None,
    downloaded_at: str | None = None,
    extracted_at: str | None = None,
) -> dict[str, object]:
    return {
        "demo_record_id": build_demo_record_id(row, dem_path),
        "series_id": clean_string(row.get("series_id")),
        "hltv_match_id": clean_string(row.get("hltv_match_id")),
        "match_url": clean_string(row.get("match_url")),
        "match_date": clean_string(row.get("match_date")),
        "event_name": clean_string(row.get("event_name")),
        "target_team": clean_string(row.get("target_team")),
        "opponent": clean_string(row.get("opponent")),
        "map_name": clean_string(row.get("map_name")),
        "map_number": clean_string(row.get("map_number")),
        "demo_link": clean_string(row.get("demo_link")),
        "archive_url": archive_url,
        "archive_path": str(archive_path) if archive_path else None,
        "archive_file_name": archive_path.name if archive_path else None,
        "archive_file_size_bytes": archive_file_size_bytes,
        "archive_sha256": archive_sha256,
        "dem_path": str(dem_path) if dem_path else None,
        "dem_file_name": dem_path.name if dem_path else None,
        "dem_file_size_bytes": dem_file_size_bytes,
        "dem_sha256": dem_sha256,
        "download_status": download_status,
        "extract_status": extract_status,
        "status": status,
        "error_message": error_message,
        "downloaded_at": downloaded_at,
        "extracted_at": extracted_at,
    }


def row_from_download(
    row: dict[str, object],
    demo_link: str,
    archive_path: Path,
    download_result: DownloadResult,
    extract_status: str,
    status: str,
    error_message: str | None,
    *,
    dem_path: Path | None = None,
    dem_file_size_bytes: int | None = None,
    dem_sha256: str | None = None,
    extracted_at: str | None = None,
) -> dict[str, object]:
    row = dict(row)
    row["demo_link"] = demo_link
    return base_manifest_row(
        row,
        archive_url=download_result.final_url or demo_link,
        archive_path=archive_path,
        download_status=download_result.status,
        extract_status=extract_status,
        status=status,
        error_message=error_message,
        archive_file_size_bytes=download_result.file_size_bytes,
        archive_sha256=download_result.sha256,
        dem_path=dem_path,
        dem_file_size_bytes=dem_file_size_bytes,
        dem_sha256=dem_sha256,
        downloaded_at=download_result.downloaded_at,
        extracted_at=extracted_at,
    )


def build_demo_record_id(row: dict[str, object], dem_path: Path | None = None) -> str:
    base = build_demo_base_name(row)
    if dem_path:
        return f"{base}_{safe_slug(dem_path.stem)}"
    return base


def build_summary(total_read: int, total_eligible: int, manifest: pd.DataFrame) -> dict[str, int]:
    if manifest.empty:
        return {
            "total_read": total_read,
            "total_eligible": total_eligible,
            "total_missing_demo_link": 0,
            "total_downloaded": 0,
            "total_skipped_existing": 0,
            "total_download_failed": 0,
            "total_blocked_remote": 0,
            "total_local_existing": 0,
            "total_missing_local_archive": 0,
            "total_local_registered": 0,
            "total_extracted": 0,
            "total_extract_failed": 0,
        }
    return {
        "total_read": total_read,
        "total_eligible": total_eligible,
        "total_missing_demo_link": int((manifest["download_status"] == "missing_demo_link").sum()),
        "total_downloaded": int((manifest["download_status"] == "downloaded").sum()),
        "total_skipped_existing": int((manifest["download_status"] == "skipped_existing").sum()),
        "total_download_failed": int((manifest["download_status"] == "failed").sum()),
        "total_blocked_remote": int((manifest["download_status"] == "blocked_remote").sum()),
        "total_local_existing": int((manifest["download_status"] == "local_existing").sum()),
        "total_missing_local_archive": int((manifest["download_status"] == "missing_local_archive").sum()),
        "total_local_registered": int((manifest["download_status"] == "local_registered").sum()),
        "total_extracted": int((manifest["extract_status"] == "extracted").sum()),
        "total_extract_failed": int((manifest["extract_status"] == "failed").sum()),
    }


def print_summary(outputs: dict[str, Path], summary: dict[str, int]) -> None:
    print("Demo download summary")
    print(f"- total de linhas do catalogo lidas: {summary['total_read']}")
    print(f"- total elegiveis para download: {summary['total_eligible']}")
    print(f"- total com demo_link ausente: {summary['total_missing_demo_link']}")
    print(f"- total baixadas: {summary['total_downloaded']}")
    print(f"- total puladas por ja existirem: {summary['total_skipped_existing']}")
    print(f"- total com falha de download: {summary['total_download_failed']}")
    print(f"- total bloqueadas pelo host remoto: {summary['total_blocked_remote']}")
    print(f"- arquivos locais encontrados: {summary['total_local_existing']}")
    print(f"- arquivos locais ausentes: {summary['total_missing_local_archive']}")
    print(f"- arquivos locais registrados por --archive-path: {summary['total_local_registered']}")
    print(f"- total extraidas: {summary['total_extracted']}")
    print(f"- total com falha de extracao: {summary['total_extract_failed']}")
    for fmt, path in outputs.items():
        print(f"- manifesto {fmt}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download CS2 demo archives and build a demo manifest.")
    parser.add_argument("--config", type=Path, required=True, help="Path to configs/project.yaml")
    parser.add_argument("--catalog", type=Path, default=None, help="Optional path to matches_catalog.parquet or .csv")
    parser.add_argument("--include-warnings", action="store_true", help="Include catalog rows with validation_status = warning")
    parser.add_argument("--dry-run", action="store_true", help="Generate manifest without downloading or extracting files")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of catalog rows processed")
    parser.add_argument("--force", action="store_true", help="Download/extract again even when files already exist")
    parser.add_argument("--no-extract", action="store_true", help="Download archives but skip extraction")
    parser.add_argument("--local-only", action="store_true", help="Use only local archives; do not make HTTP requests")
    parser.add_argument("--archive-path", type=Path, default=None, help="Register a user-provided local archive for eligible rows")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    _, outputs, summary = run_download_pipeline(
        args.config,
        catalog_path=args.catalog,
        include_warnings=args.include_warnings,
        dry_run=args.dry_run,
        limit=args.limit,
        force=True if args.force else None,
        no_extract=args.no_extract,
        local_only=args.local_only,
        archive_path=args.archive_path,
    )
    print_summary(outputs, summary)


if __name__ == "__main__":
    main()
