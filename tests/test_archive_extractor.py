from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

from src.ingestion.archive_extractor import ArchiveExtractor, build_demo_base_name, detect_archive_type


def test_build_demo_base_name_is_safe() -> None:
    row = {"series_id": "hltv_123", "map_name": "de Mirage", "map_number": "1"}

    assert build_demo_base_name(row) == "hltv_123_de_mirage_map1"


def test_zip_extraction_with_fake_dem(tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.zip"
    output_dir = tmp_path / "demos"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("inside/test.dem", b"fake demo bytes")

    result = ArchiveExtractor().extract(archive_path, output_dir, "hltv_1_mirage_map1")

    assert result.status == "extracted"
    assert len(result.demos) == 1
    assert result.demos[0].path is not None
    assert result.demos[0].path.read_bytes() == b"fake demo bytes"


def test_rar_without_external_tool_is_controlled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("src.ingestion.archive_extractor.shutil.which", lambda _: None)
    monkeypatch.setattr("src.ingestion.archive_extractor.Path.exists", lambda _: False)
    archive_path = tmp_path / "archive.rar"

    result = ArchiveExtractor().extract(archive_path, tmp_path / "demos", "hltv_1_mirage_map1")

    assert result.status == "unsupported_archive"
    assert "requires 7z" in (result.error_message or "")


def test_rar_extraction_finds_dem_inside_subfolder(monkeypatch, tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.rar"
    output_dir = tmp_path / "demos"
    archive_path.write_bytes(b"fake rar bytes")

    monkeypatch.setattr("src.ingestion.archive_extractor.shutil.which", lambda _: "7z")

    def fake_run(command, capture_output, text, check):
        extraction_dir = Path(next(value[2:] for value in command if value.startswith("-o")))
        nested_dir = extraction_dir / "nested"
        nested_dir.mkdir(parents=True)
        (nested_dir / "inside.dem").write_bytes(b"fake demo")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("src.ingestion.archive_extractor.subprocess.run", fake_run)

    result = ArchiveExtractor().extract(archive_path, output_dir, "hltv_1_mirage_map1")

    assert result.status == "extracted"
    assert len(result.demos) == 1
    assert result.demos[0].path == output_dir / "hltv_1_mirage_map1_inside.dem"


def test_rar_rerun_returns_existing_demos_without_renaming(monkeypatch, tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.rar"
    output_dir = tmp_path / "demos"
    output_dir.mkdir()
    archive_path.write_bytes(b"fake rar bytes")
    existing = output_dir / "hltv_1_mirage_map1_inside.dem"
    existing.write_bytes(b"existing demo")

    monkeypatch.setattr("src.ingestion.archive_extractor.shutil.which", lambda _: "7z")

    def fake_run(command, capture_output, text, check):
        extraction_dir = Path(next(value[2:] for value in command if value.startswith("-o")))
        extraction_dir.mkdir(parents=True, exist_ok=True)
        (extraction_dir / "inside.dem").write_bytes(b"existing demo")
        return SimpleNamespace(returncode=0, stdout="Everything is Ok", stderr="")

    monkeypatch.setattr("src.ingestion.archive_extractor.subprocess.run", fake_run)

    result = ArchiveExtractor().extract(archive_path, output_dir, "hltv_1_mirage_map1")

    assert result.status == "skipped_existing"
    assert len(result.demos) == 1
    assert result.demos[0].status == "skipped_existing"
    assert result.demos[0].path == existing
    assert not (output_dir / "hltv_1_mirage_map1_hltv_1_mirage_map1_inside.dem").exists()


def test_rar_rerun_rejects_changed_archive_member(monkeypatch, tmp_path: Path) -> None:
    archive_path = tmp_path / "archive.rar"
    output_dir = tmp_path / "demos"
    output_dir.mkdir()
    archive_path.write_bytes(b"fake rar bytes")
    existing = output_dir / "hltv_1_mirage_map1_inside.dem"
    existing.write_bytes(b"old demo")

    monkeypatch.setattr("src.ingestion.archive_extractor.shutil.which", lambda _: "7z")

    def fake_run(command, capture_output, text, check):
        extraction_dir = Path(next(value[2:] for value in command if value.startswith("-o")))
        extraction_dir.mkdir(parents=True, exist_ok=True)
        (extraction_dir / "inside.dem").write_bytes(b"changed demo")
        return SimpleNamespace(returncode=0, stdout="Everything is Ok", stderr="")

    monkeypatch.setattr("src.ingestion.archive_extractor.subprocess.run", fake_run)

    result = ArchiveExtractor().extract(archive_path, output_dir, "hltv_1_mirage_map1")

    assert result.status == "failed"
    assert result.demos == []
    assert "differs from archive member" in (result.error_message or "")
    assert existing.read_bytes() == b"old demo"


def test_detect_archive_type() -> None:
    assert detect_archive_type(Path("a.dem")) == "dem"
    assert detect_archive_type(Path("a.zip")) == "zip"
    assert detect_archive_type(Path("a.rar")) == "rar"
