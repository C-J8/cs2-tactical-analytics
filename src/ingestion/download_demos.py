from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from src.config.schemas import ProjectConfig, load_project_config
from src.ingestion.archive_extractor import build_demo_base_name
from src.ingestion.demo_downloader import DemoDownloader, DownloadResult, sha256_file
from src.ingestion.hltv_client import HltvClient, parse_match_page
from src.utils.io import default_catalog_path, ensure_dir, read_catalog, write_manifest
from src.utils.logging import configure_logging
from src.utils.text import clean_string

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
    "download_status",
    "archive_ready_for_scan",
    "manual_action_required",
    "manual_download_page",
    "expected_archive_directory",
    "expected_archive_stem",
    "manual_registration_command",
    "status",
    "error_message",
    "downloaded_at",
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
    local_only: bool = False,
    archive_path: Path | None = None,
    match_id: str | None = None,
    series_id: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Path], dict[str, int]]:
    project = load_project_config(config_path)
    if archive_path is not None and not archive_path.exists():
        raise FileNotFoundError(f"Local archive not found: {archive_path}")
    catalog_path = catalog_path or default_catalog_path(project.silver_output_dir)
    catalog = read_catalog(catalog_path)
    total_read = len(catalog)
    eligible = select_eligible_rows(catalog, include_warnings=include_warnings)
    eligible = filter_selected_rows(eligible, match_id=match_id, series_id=series_id)

    run_limit = limit if limit is not None else project.max_downloads_per_run
    if run_limit is not None and (dry_run or local_only or archive_path is not None):
        eligible = eligible.head(run_limit)
    if archive_path is not None and len(eligible) != 1:
        raise ValueError("--archive-path requires exactly one eligible row; use --match-id or --series-id")

    manifest_rows = process_rows(
        eligible,
        project,
        dry_run=dry_run,
        force=project.force_download if force is None else force,
        local_only=local_only,
        archive_path=archive_path,
        download_limit=run_limit,
    )
    manifest = pd.DataFrame(manifest_rows, columns=MANIFEST_COLUMNS)
    outputs = write_manifest(manifest, project.demo_manifest_dir, project.output_formats)
    summary = build_summary(total_read, len(eligible), manifest)
    return manifest, outputs, summary


def select_eligible_rows(catalog: pd.DataFrame, *, include_warnings: bool = False) -> pd.DataFrame:
    if include_warnings:
        eligible = catalog[catalog["validation_status"].isin(["ok", "warning"])].copy()
    else:
        eligible = catalog[catalog["validation_status"] == "ok"].copy()
    if eligible.empty:
        return eligible
    acquisition_keys = eligible.apply(acquisition_key, axis=1)
    return eligible.loc[~acquisition_keys.duplicated()].copy()


def acquisition_key(row: pd.Series) -> str:
    for field in ("series_id", "hltv_match_id", "demo_link", "match_url"):
        value = clean_string(row.get(field))
        if value:
            return f"{field}:{value}"
    return f"row:{row.name}"


def filter_selected_rows(
    rows: pd.DataFrame,
    *,
    match_id: str | None,
    series_id: str | None,
) -> pd.DataFrame:
    if match_id and series_id:
        raise ValueError("Use only one selector: --match-id or --series-id")
    if match_id:
        return rows[rows["hltv_match_id"].astype("string") == str(match_id)].copy()
    if series_id:
        return rows[rows["series_id"].astype("string") == str(series_id)].copy()
    return rows


def process_rows(
    rows: pd.DataFrame,
    project: ProjectConfig,
    *,
    dry_run: bool,
    force: bool,
    local_only: bool = False,
    archive_path: Path | None = None,
    download_limit: int | None = None,
) -> list[dict[str, object]]:
    manifest_rows: list[dict[str, object]] = []
    downloader: DemoDownloader | None = None
    hltv_client: HltvClient | None = None
    remote_attempts = 0

    for _, row in rows.iterrows():
        row_dict = row.to_dict()
        demo_link = clean_string(row_dict.get("demo_link"))

        if dry_run and not demo_link and not local_only and archive_path is None:
            manifest_rows.append(
                base_manifest_row(
                    row_dict,
                    archive_path=expected_local_archive_paths(project.demo_archive_dir, row_dict)[-1],
                    download_status="missing_demo_link",
                    status="warning",
                    error_message="demo_link is missing",
                    manual_action_required=True,
                )
            )
            continue

        if dry_run:
            planned_archive_path = build_archive_path(project.demo_archive_dir, row_dict, demo_link or "")
            manifest_rows.append(
                base_manifest_row(
                    row_dict,
                    archive_url=demo_link,
                    archive_path=planned_archive_path,
                    download_status="dry_run",
                    status="warning",
                    error_message="dry run: no archive downloaded",
                )
            )
            continue

        if archive_path is not None:
            manifest_rows.extend(process_explicit_archive(row_dict, archive_path, project, force=force))
            continue

        if local_only:
            manifest_rows.extend(process_local_archive(row_dict, project))
            continue

        if not demo_link and project.mode in {"scrape", "hybrid"}:
            if hltv_client is None:
                hltv_client = HltvClient(
                    project.hltv_cache_dir,
                    cache_enabled=project.cache_enabled,
                    rate_limit_seconds=project.rate_limit_seconds,
                )
            demo_link = try_enrich_demo_link(row_dict, hltv_client)
            row_dict["demo_link"] = demo_link

        if not force and find_local_archive(project.demo_archive_dir, row_dict) is not None:
            manifest_rows.extend(process_local_archive(row_dict, project))
            continue

        if not demo_link:
            manifest_rows.append(
                base_manifest_row(
                    row_dict,
                    archive_path=expected_local_archive_paths(project.demo_archive_dir, row_dict)[-1],
                    download_status="missing_demo_link",
                    status="warning",
                    error_message="demo_link is missing",
                    manual_action_required=True,
                )
            )
            continue

        planned_archive_path = build_archive_path(project.demo_archive_dir, row_dict, demo_link)
        if download_limit is not None and remote_attempts >= download_limit:
            continue
        remote_attempts += 1
        if downloader is None:
            downloader = DemoDownloader(timeout_seconds=project.download_timeout_seconds)
        match_url = clean_string(row_dict.get("match_url"))
        downloader.prime_match_page(match_url)
        download_result = downloader.download(demo_link, planned_archive_path, force=force, referer=match_url)
        if download_result.status in {"failed", "blocked_remote"}:
            failed_archive_path = download_result.path or planned_archive_path
            status = "warning" if download_result.status == "blocked_remote" else "failed"
            manifest_rows.append(
                row_from_download(
                    row_dict,
                    demo_link,
                    failed_archive_path,
                    download_result,
                    status,
                    download_result.error_message,
                    manual_action_required=True,
                )
            )
            continue

        actual_archive_path = download_result.path or planned_archive_path
        manifest_rows.append(
            row_from_download(
                row_dict,
                demo_link,
                actual_archive_path,
                download_result,
                "ok",
                None,
                archive_ready_for_scan=True,
            )
        )

        if project.download_rate_limit_seconds > 0:
            time.sleep(project.download_rate_limit_seconds)

    return manifest_rows


def process_local_archive(
    row: dict[str, object],
    project: ProjectConfig,
) -> list[dict[str, object]]:
    local_archive = find_local_archive(project.demo_archive_dir, row)
    if local_archive is None:
        expected = [str(path) for path in expected_local_archive_paths(project.demo_archive_dir, row)]
        return [
            base_manifest_row(
                row,
                archive_path=expected_local_archive_paths(project.demo_archive_dir, row)[-1],
                download_status="missing_local_archive",
                status="warning",
                error_message=f"Local archive not found for base name {build_demo_base_name(row)}. Expected one of: {', '.join(expected)}",
                manual_action_required=True,
            )
        ]
    download_result = local_download_result("local_existing", local_archive)
    return [
        row_from_download(
            row,
            clean_string(row.get("demo_link")) or "",
            local_archive,
            download_result,
            "ok",
            None,
            archive_ready_for_scan=True,
        )
    ]


def process_explicit_archive(
    row: dict[str, object],
    source_archive_path: Path,
    project: ProjectConfig,
    *,
    force: bool,
) -> list[dict[str, object]]:
    target_archive_path = expected_archive_path(project.demo_archive_dir, row, source_archive_path.suffix.lower())
    ensure_dir(target_archive_path.parent)
    if source_archive_path.resolve() != target_archive_path.resolve() and (force or not target_archive_path.exists()):
        shutil.copy2(source_archive_path, target_archive_path)
    download_result = local_download_result("local_registered", target_archive_path)
    return [
        row_from_download(
            row,
            clean_string(row.get("demo_link")) or "",
            target_archive_path,
            download_result,
            "ok",
            None,
            archive_ready_for_scan=True,
        )
    ]


def local_download_result(status: str, archive_path: Path) -> DownloadResult:
    return DownloadResult(
        status=status,
        path=archive_path,
        file_size_bytes=archive_path.stat().st_size,
        sha256=sha256_file(archive_path),
        downloaded_at=None,
    )


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
    status: str,
    error_message: str | None,
    archive_file_size_bytes: int | None = None,
    archive_sha256: str | None = None,
    downloaded_at: str | None = None,
    archive_ready_for_scan: bool = False,
    manual_action_required: bool = False,
) -> dict[str, object]:
    fallback = manual_fallback_fields(row, archive_path) if manual_action_required else {}
    return {
        "demo_record_id": build_demo_record_id(row),
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
        "download_status": download_status,
        "archive_ready_for_scan": archive_ready_for_scan,
        "manual_action_required": manual_action_required,
        "manual_download_page": fallback.get("manual_download_page"),
        "expected_archive_directory": fallback.get("expected_archive_directory"),
        "expected_archive_stem": fallback.get("expected_archive_stem"),
        "manual_registration_command": fallback.get("manual_registration_command"),
        "status": status,
        "error_message": error_message,
        "downloaded_at": downloaded_at,
    }


def row_from_download(
    row: dict[str, object],
    demo_link: str,
    archive_path: Path,
    download_result: DownloadResult,
    status: str,
    error_message: str | None,
    *,
    archive_ready_for_scan: bool = False,
    manual_action_required: bool = False,
) -> dict[str, object]:
    row = dict(row)
    row["demo_link"] = demo_link
    return base_manifest_row(
        row,
        archive_url=download_result.final_url or demo_link,
        archive_path=archive_path,
        download_status=download_result.status,
        status=status,
        error_message=error_message,
        archive_file_size_bytes=download_result.file_size_bytes,
        archive_sha256=download_result.sha256,
        downloaded_at=download_result.downloaded_at,
        archive_ready_for_scan=archive_ready_for_scan,
        manual_action_required=manual_action_required,
    )


def manual_fallback_fields(row: dict[str, object], archive_path: Path | None) -> dict[str, str | None]:
    match_id = clean_string(row.get("hltv_match_id"))
    series_id = clean_string(row.get("series_id"))
    selector = f"--match-id {match_id}" if match_id else (f"--series-id {series_id}" if series_id else "")
    expected_directory = str(archive_path.parent) if archive_path else None
    return {
        "manual_download_page": clean_string(row.get("match_url")) or clean_string(row.get("demo_link")),
        "expected_archive_directory": expected_directory,
        "expected_archive_stem": build_demo_base_name(row),
        "manual_registration_command": (
            "python -m src.ingestion.download_demos --config configs/project.yaml "
            f"{selector} --archive-path \"<arquivo_baixado>\" --require-ready"
        ),
    }


def build_demo_record_id(row: dict[str, object]) -> str:
    return build_demo_base_name(row)


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
            "total_ready_for_scanner": 0,
            "total_not_ready": 0,
            "total_manual_action_required": 0,
            "total_processed": 0,
            "total_deferred_by_limit": total_eligible,
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
        "total_ready_for_scanner": int(manifest["archive_ready_for_scan"].fillna(False).sum()),
        "total_not_ready": int((~manifest["archive_ready_for_scan"].fillna(False).astype(bool)).sum()),
        "total_manual_action_required": int(manifest["manual_action_required"].fillna(False).sum()),
        "total_processed": len(manifest),
        "total_deferred_by_limit": max(total_eligible - len(manifest), 0),
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
    print(f"- arquivos prontos para scan/extracao: {summary['total_ready_for_scanner']}")
    print(f"- arquivos ainda nao prontos: {summary['total_not_ready']}")
    print(f"- pendencias com acao manual: {summary['total_manual_action_required']}")
    print(f"- registros processados nesta execucao: {summary['total_processed']}")
    print(f"- registros adiados pelo limite do lote: {summary['total_deferred_by_limit']}")
    for fmt, path in outputs.items():
        print(f"- manifesto {fmt}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Acquire CS2 demo archives and build an acquisition manifest.")
    parser.add_argument("--config", type=Path, required=True, help="Path to configs/project.yaml")
    parser.add_argument("--catalog", type=Path, default=None, help="Optional path to matches_catalog.parquet or .csv")
    parser.add_argument("--include-warnings", action="store_true", help="Include catalog rows with validation_status = warning")
    parser.add_argument("--dry-run", action="store_true", help="Generate manifest without downloading or extracting files")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of catalog rows processed")
    parser.add_argument("--force", action="store_true", help="Download or register the archive again when it exists")
    parser.add_argument("--local-only", action="store_true", help="Use only local archives; do not make HTTP requests")
    parser.add_argument("--archive-path", type=Path, default=None, help="Register a user-provided local archive for eligible rows")
    parser.add_argument("--match-id", default=None, help="Process only one HLTV match id")
    parser.add_argument("--series-id", default=None, help="Process only one canonical series id")
    parser.add_argument("--require-ready", action="store_true", help="Exit non-zero when any selected archive is not ready")
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
        local_only=args.local_only,
        archive_path=args.archive_path,
        match_id=args.match_id,
        series_id=args.series_id,
    )
    print_summary(outputs, summary)
    if args.require_ready and summary["total_not_ready"]:
        raise SystemExit("Archive acquisition is incomplete; inspect demo_manifest for the manual fallback action")


if __name__ == "__main__":
    main()
