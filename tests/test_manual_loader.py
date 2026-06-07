from pathlib import Path

from src.ingestion.manual_loader import EXPECTED_MANUAL_COLUMNS, load_manual_matches


def test_load_manual_matches_adds_missing_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "seed.csv"
    csv_path.write_text("hltv_match_id,match_url\n1,https://www.hltv.org/matches/1/example\n", encoding="utf-8")

    df = load_manual_matches(csv_path)

    assert list(df.columns) == EXPECTED_MANUAL_COLUMNS
    assert len(df) == 1
