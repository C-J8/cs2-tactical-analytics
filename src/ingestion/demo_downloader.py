from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.utils.io import ensure_dir

LOGGER = logging.getLogger(__name__)


@dataclass
class DownloadResult:
    status: str
    path: Path | None
    file_size_bytes: int | None
    sha256: str | None
    downloaded_at: str | None
    final_url: str | None = None
    error_message: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DemoDownloader:
    def __init__(self, *, timeout_seconds: int = 60, chunk_size: int = 1024 * 1024) -> None:
        self.timeout_seconds = timeout_seconds
        self.chunk_size = chunk_size
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                ),
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def prime_match_page(self, match_url: str | None) -> None:
        if not match_url:
            return
        try:
            response = self.session.get(
                match_url,
                timeout=self.timeout_seconds,
                allow_redirects=True,
                headers={"Referer": "https://www.hltv.org/"},
            )
            response.close()
        except requests.RequestException as exc:
            LOGGER.info("Could not prime downloader session with match page %s: %s", match_url, exc)

    def download(self, url: str, output_path: Path, *, force: bool = False, referer: str | None = None) -> DownloadResult:
        ensure_dir(output_path.parent)
        if output_path.suffix != ".download" and output_path.exists() and not force:
            return self._existing_result(output_path)

        temp_path: Path | None = None
        final_url: str | None = None
        try:
            request_headers = {"Referer": referer or "https://www.hltv.org/"}
            with self.session.get(url, stream=True, timeout=self.timeout_seconds, allow_redirects=True, headers=request_headers) as response:
                final_url = response.url
                output_path = resolve_download_path(output_path, response.url, response.headers.get("Content-Disposition"))
                response.raise_for_status()
                ensure_dir(output_path.parent)
                if output_path.exists() and not force:
                    return self._existing_result(output_path)
                temp_path = output_path.with_suffix(output_path.suffix + ".part")
                with temp_path.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if chunk:
                            file.write(chunk)
            if output_path.exists() and force:
                output_path.unlink()
            temp_path.replace(output_path)
        except requests.RequestException as exc:
            LOGGER.warning("Demo download failed for %s: %s", url, exc)
            if temp_path and temp_path.exists():
                temp_path.unlink()
            status = "blocked_remote" if _is_remote_block(exc) else "failed"
            return DownloadResult(status, output_path, None, None, None, final_url, str(exc))
        except OSError as exc:
            LOGGER.warning("Could not save demo archive %s: %s", output_path, exc)
            if temp_path and temp_path.exists():
                temp_path.unlink()
            return DownloadResult("failed", output_path, None, None, None, final_url, str(exc))

        return DownloadResult(
            status="downloaded",
            path=output_path,
            file_size_bytes=output_path.stat().st_size,
            sha256=sha256_file(output_path),
            downloaded_at=datetime.now(timezone.utc).isoformat(),
            final_url=final_url,
        )

    def _existing_result(self, output_path: Path) -> DownloadResult:
        return DownloadResult(
            status="skipped_existing",
            path=output_path,
            file_size_bytes=output_path.stat().st_size,
            sha256=sha256_file(output_path),
            downloaded_at=None,
            final_url=None,
        )


def resolve_download_path(output_path: Path, final_url: str | None, content_disposition: str | None) -> Path:
    extension = detect_download_extension(final_url, content_disposition)
    if not extension or output_path.suffix.lower() != ".download":
        return output_path
    return output_path.with_suffix(extension)


def detect_download_extension(final_url: str | None, content_disposition: str | None) -> str | None:
    for candidate in (_extension_from_content_disposition(content_disposition), _extension_from_url(final_url)):
        if candidate in {".rar", ".zip", ".dem", ".7z"}:
            return candidate
    return None


def _extension_from_url(url: str | None) -> str | None:
    if not url:
        return None
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix or None


def _extension_from_content_disposition(content_disposition: str | None) -> str | None:
    if not content_disposition:
        return None
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', content_disposition, flags=re.IGNORECASE)
    if not match:
        return None
    return Path(match.group(1)).suffix.lower() or None


def _is_remote_block(exc: requests.RequestException) -> bool:
    response = getattr(exc, "response", None)
    return response is not None and response.status_code in {403, 429}
