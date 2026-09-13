import io
from zipfile import ZipFile

from src.maps.sync_awpy_map_assets import safe_relative_path, selected_members


def test_map_asset_selection_keeps_only_requested_map() -> None:
    payload = io.BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr("radars/de_mirage.png", b"mirage")
        archive.writestr("radars/de_inferno.png", b"inferno")
    payload.seek(0)

    with ZipFile(payload) as archive:
        assert selected_members(archive, "de_mirage") == ["radars/de_mirage.png"]
    assert safe_relative_path("radars/de_mirage.png").as_posix() == "radars/de_mirage.png"
