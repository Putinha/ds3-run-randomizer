import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import run_tests
from randomizer import (
    generate_valid_seed,
    load_database,
    load_seed,
    randomize,
    save_seed,
    validate_randomized_placement,
)


def test_randomizer_is_deterministic():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    areas, weapons, locations = load_database(base_dir)
    placements_a = randomize(12345, areas, weapons, locations)
    placements_b = randomize(12345, areas, weapons, locations)
    assert placements_a == placements_b


def test_randomizer_differs_for_different_seeds():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    areas, weapons, locations = load_database(base_dir)
    placements_a = randomize(12345, areas, weapons, locations)
    placements_b = randomize(54321, areas, weapons, locations)
    assert placements_a != placements_b


def test_randomizer_covers_all_weapons_once():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    areas, weapons, locations = load_database(base_dir)
    placements = randomize(7, areas, weapons, locations)

    assigned_weapons = []
    for weapon_name in placements.values():
        if isinstance(weapon_name, list):
            assigned_weapons.extend(weapon_name)
        else:
            assigned_weapons.append(weapon_name)

    weapon_names = {weapon["name"] for weapon in weapons}
    assert len(assigned_weapons) == len(weapon_names)
    assert len(assigned_weapons) == len(set(assigned_weapons))
    assert set(assigned_weapons).issubset(weapon_names)


def test_randomizer_prevents_duplicates_and_keeps_starting_equipment():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    areas, weapons, locations = load_database(base_dir)
    placements = randomize(99, areas, weapons, locations)

    starting_ids = [
        loc_id
        for loc_id, loc in locations.items()
        if loc.get("source") == "starting_equipment"
    ]
    for loc_id in starting_ids:
        assert placements[loc_id] == locations[loc_id]["item"]


def test_randomized_placement_is_progression_valid():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    areas, weapons, locations = load_database(base_dir)
    placements = randomize(1234, areas, weapons, locations)
    validation = validate_randomized_placement(placements, areas, locations, seed=1234)
    assert validation["valid"] is True


def test_randomized_placement_reaches_all_locations():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    areas, weapons, locations = load_database(base_dir)
    placements = randomize(777, areas, weapons, locations)
    validation = validate_randomized_placement(placements, areas, locations, seed=777)

    assert validation["valid"] is True
    assert validation["unreachable_locations"] == []
    assert len(validation["reachable_locations"]) == len(locations)


def test_randomized_placement_detects_item_dependency_deadlock():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    areas, weapons, locations = load_database(base_dir)

    test_locations = {
        "start": {
            "name": "Start",
            "area": "Cemetery of Ash",
            "item": "Weapon A",
            "source": "corpse",
            "requires": None,
        },
        "locked": {
            "name": "Locked",
            "area": "Cemetery of Ash",
            "item": "Weapon B",
            "source": "corpse",
            "requires": {
                "all": [
                    {"type": "item_obtained", "target": "Weapon C"}
                ]
            },
        },
    }
    test_placements = {
        "start": "Weapon A",
        "locked": "Weapon B",
    }

    validation = validate_randomized_placement(
        test_placements, areas, test_locations, seed=1
    )

    assert validation["valid"] is False
    assert validation["unreachable_locations"] == ["locked"]
    assert validation["blocked_locations"] == ["locked"]


def test_randomized_placement_is_stable_across_many_seeds():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    areas, weapons, locations = load_database(base_dir)

    for seed in range(100):
        placements = randomize(seed, areas, weapons, locations)
        validation = validate_randomized_placement(
            placements, areas, locations, seed=seed
        )
        assert validation["valid"] is True, (seed, validation["reasons"])


def test_generate_valid_seed_returns_seed_and_placements():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    result = generate_valid_seed(420, base_dir=base_dir, max_attempts=25)
    assert result["seed"] == 420
    assert len(result["placements"]) == len(load_database(base_dir)[2])


def test_save_and_load_seed_round_trip(tmp_path):
    placements = {"loc_a": "Weapon A", "loc_b": "Weapon B"}
    path = save_seed(placements, 123, base_dir=str(tmp_path))
    loaded = load_seed(path)
    assert loaded["seed"] == 123
    assert loaded["placements"] == placements


def test_invalid_seed_input_is_rejected():
    with pytest.raises((ValueError, TypeError)):
        randomize("bad-seed", {}, [], {})


def test_run_tests_passes():
    _, failures = run_tests(os.path.dirname(os.path.dirname(__file__)))
    assert failures == []
