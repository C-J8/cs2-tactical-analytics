import pandas as pd

from src.features.demo_timing import TimingContract, build_demo_timing


def test_demo_timing_uses_contract_and_validates_freeze_duration() -> None:
    eligible = pd.DataFrame(
        [
            {"parse_id": "p1", "dem_file_id": "d1", "series_id": "s1", "inferred_map_name": "Mirage"},
            {"parse_id": "p2", "dem_file_id": "d2", "series_id": "s2", "inferred_map_name": "Mirage"},
        ]
    )
    rounds = pd.DataFrame(
        [
            {"source_parse_id": parse_id, "start": 1000, "freeze_end": 2280}
            for parse_id in ("p1", "p2")
        ]
    )
    contract = TimingContract("v1", 64.0, "project_assumption", "assumed", 20.0, 1.0, ())

    timing, audit = build_demo_timing(eligible, rounds, contract)

    assert timing["tickrate"].tolist() == [64.0, 64.0]
    assert timing["tickrate_resolution_method"].eq("contract_default").all()
    assert audit["median_freeze_seconds"].eq(20.0).all()
    assert audit["timing_evidence_status"].eq("consistent").all()
