from __future__ import annotations

from pathlib import Path

import requests

from src.ingestion.demo_downloader import DemoDownloader, detect_download_extension, sha256_file


class _FakeResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        url: str = "https://example.test/demo.zip",
        headers: dict[str, str] | None = None,
        status_code: int = 200,
    ) -> None:
        self.chunks = chunks
        self.url = url
        self.headers = headers or {}
        self.status_code = status_code

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def close(self) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} Client Error")
            error.response = self
            raise error
        return None

    def iter_content(self, chunk_size: int):
        yield from self.chunks


class _FakeSession:
    def __init__(self, response: _FakeResponse | None = None) -> None:
        self.headers = {}
        self.response = response or _FakeResponse([b"abc", b"123"])
        self.urls: list[str] = []

    def get(self, url: str, stream: bool = False, timeout: int = 10, allow_redirects: bool = True, headers: dict[str, str] | None = None) -> _FakeResponse:
        self.urls.append(url)
        assert allow_redirects is True
        assert timeout == 10
        assert headers is not None
        return self.response


def test_download_with_mocked_requests_saves_file(tmp_path: Path) -> None:
    output_path = tmp_path / "demo.zip"
    downloader = DemoDownloader(timeout_seconds=10)
    downloader.session = _FakeSession()

    result = downloader.download("https://example.test/demo.zip", output_path)

    assert result.status == "downloaded"
    assert output_path.read_bytes() == b"abc123"
    assert result.file_size_bytes == 6
    assert result.sha256 == sha256_file(output_path)


def test_existing_file_skips_download(tmp_path: Path) -> None:
    output_path = tmp_path / "demo.zip"
    output_path.write_bytes(b"already here")
    downloader = DemoDownloader(timeout_seconds=10)

    result = downloader.download("https://example.test/demo.zip", output_path)

    assert result.status == "skipped_existing"
    assert result.file_size_bytes == output_path.stat().st_size


def test_download_uses_final_redirect_extension_for_hltv_style_link(tmp_path: Path) -> None:
    output_path = tmp_path / "hltv_42_mirage_map1.download"
    downloader = DemoDownloader(timeout_seconds=10)
    downloader.session = _FakeSession(_FakeResponse([b"rar bytes"], url="https://replay.example.test/hltv_42.rar"))

    result = downloader.download("https://www.hltv.org/download/demo/42", output_path)

    assert result.status == "downloaded"
    assert result.path == tmp_path / "hltv_42_mirage_map1.rar"
    assert result.path.read_bytes() == b"rar bytes"
    assert not output_path.exists()


def test_detect_download_extension_prefers_content_disposition() -> None:
    extension = detect_download_extension(
        "https://example.test/download/demo/42",
        'attachment; filename="hltv_42_mirage_map1.zip"',
    )

    assert extension == ".zip"


def test_blocked_remote_status_for_403_after_redirect(tmp_path: Path) -> None:
    output_path = tmp_path / "hltv_42_mirage_map1.download"
    downloader = DemoDownloader(timeout_seconds=10)
    downloader.session = _FakeSession(
        _FakeResponse([], url="https://r2-demos.hltv.org/demo.rar", status_code=403)
    )

    result = downloader.download("https://www.hltv.org/download/demo/42", output_path)

    assert result.status == "blocked_remote"
    assert result.path == tmp_path / "hltv_42_mirage_map1.rar"
    assert result.final_url == "https://r2-demos.hltv.org/demo.rar"


def test_prime_match_page_uses_same_session() -> None:
    fake_session = _FakeSession()
    downloader = DemoDownloader(timeout_seconds=10)
    downloader.session = fake_session

    downloader.prime_match_page("https://www.hltv.org/matches/42/example")

    assert fake_session.urls == ["https://www.hltv.org/matches/42/example"]
