from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd

from src.parsing.awpy_parser import AwpyParser, normalize_events, to_pandas


def test_awpy_parser_mock(monkeypatch, tmp_path) -> None:
    class FakeDemo:
        def __init__(self, path: str, verbose: bool) -> None:
            self.path = path
            self.verbose = verbose
            self.rounds = pd.DataFrame({"round_num": [1, 2]})
            self.grenades = pd.DataFrame({"grenade_type": ["smoke"]})
            self.ticks = pd.DataFrame({"tick": [1], "X": [10]})
            self.events = {"player_death": pd.DataFrame({"tick": [2]})}

        def parse(self, player_props: list[str]) -> None:
            self.player_props = player_props

    monkeypatch.setitem(sys.modules, "awpy", SimpleNamespace(Demo=FakeDemo))
    dem_path = tmp_path / "fake.dem"
    dem_path.write_bytes(b"fake")

    parsed = AwpyParser(
        player_props=["X", "Y"],
        parse_tables=["rounds", "grenades", "ticks"],
        parse_events=True,
    ).parse(dem_path)

    assert len(parsed.tables["rounds"]) == 2
    assert len(parsed.tables["grenades"]) == 1
    assert len(parsed.tables["ticks"]) == 1
    assert len(parsed.events["player_death"]) == 1


def test_to_pandas_handles_none_and_dict() -> None:
    assert to_pandas(None).empty
    assert list(to_pandas({"a": [1]}).columns) == ["a"]


def test_normalize_events_handles_dataframe() -> None:
    events = normalize_events(pd.DataFrame({"tick": [1]}))

    assert "events" in events
    assert len(events["events"]) == 1
