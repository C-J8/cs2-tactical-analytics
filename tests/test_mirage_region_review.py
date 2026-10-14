from src.validation.mirage_region_review import world_to_radar


def test_world_to_radar_uses_pinned_mirage_transform() -> None:
    transform = {"pos_x": -3230.0, "pos_y": 1713.0, "scale": 5.0}

    x, y = world_to_radar(-423.4422, -1922.2833, transform)

    assert round(x, 3) == 561.312
    assert round(y, 3) == 727.057
