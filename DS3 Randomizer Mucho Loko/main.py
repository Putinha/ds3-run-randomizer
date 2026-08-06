import argparse
import json
import os
import random
import sys
import tempfile

from engine.progression import (
    get_accessible_areas,
    get_accessible_items,
    requirement_met,
)
from engine.validate import validate_database
from randomizer import (
    build_randomizer_output,
    load_database,
    load_seed,
    randomize,
    generate_valid_seed,
    save_randomizer_result,
    save_seed,
    validate_randomized_placement,
    validate_randomizer_output,
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def empty_state():
    return {
        "bosses_defeated": [],
        "areas_reached": [],
        "items_obtained": [],
        "gestures_obtained": [],
        "npcs_available": [],
    }


def area_name_to_id(areas, area_name):
    for area_id, area in areas.items():
        if area["name"] == area_name:
            return area_id
    return None


def is_area_accessible(areas, state, area_name):
    accessible_areas = get_accessible_areas(areas, state)
    area_id = area_name_to_id(areas, area_name)
    return area_id in accessible_areas


def assert_true(condition, message, failures):
    if not condition:
        failures.append(message)


def test_requirement_met(areas, failures):
    empty = empty_state()
    accessible_areas = set()

    assert_true(
        requirement_met(None, areas, accessible_areas, empty),
        "requirement=null must return True",
        failures,
    )

    assert_true(
        not requirement_met(
            {"type": "boss_defeated", "target": "Iudex Gundyr"},
            areas,
            accessible_areas,
            empty,
        ),
        "boss_defeated should fail on empty state",
        failures,
    )

    state = empty_state()
    state["bosses_defeated"] = ["Iudex Gundyr"]
    assert_true(
        requirement_met(
            {"type": "boss_defeated", "target": "Iudex Gundyr"},
            areas,
            accessible_areas,
            state,
        ),
        "boss_defeated should succeed when boss is defeated",
        failures,
    )

    state = empty_state()
    state["items_obtained"] = ["Grand Archives Key"]
    assert_true(
        requirement_met(
            {"type": "item_obtained", "target": "Grand Archives Key"},
            areas,
            accessible_areas,
            state,
        ),
        "item_obtained should succeed when item is obtained",
        failures,
    )

    state = empty_state()
    state["gestures_obtained"] = ["Path of the Dragon"]
    assert_true(
        requirement_met(
            {"type": "gesture_obtained", "target": "Path of the Dragon"},
            areas,
            accessible_areas,
            state,
        ),
        "gesture_obtained should succeed when gesture is obtained",
        failures,
    )

    state = empty_state()
    state["npcs_available"] = ["Greirat"]
    assert_true(
        requirement_met(
            {"type": "npc_available", "target": "Greirat"},
            areas,
            accessible_areas,
            state,
        ),
        "npc_available should succeed when NPC is available",
        failures,
    )

    assert_true(
        requirement_met(
            {
                "all": [
                    {"type": "boss_defeated", "target": "Iudex Gundyr"},
                    {"type": "boss_defeated", "target": "Vordt of the Boreal Valley"},
                ]
            },
            areas,
            accessible_areas,
            {
                **empty_state(),
                "bosses_defeated": [
                    "Iudex Gundyr",
                    "Vordt of the Boreal Valley",
                ],
            },
        ),
        "all requirement should succeed when every child requirement is met",
        failures,
    )

    assert_true(
        requirement_met(
            {
                "any": [
                    {"type": "boss_defeated", "target": "Sister Friede"},
                    {"type": "area_reached", "target": "Kiln of the First Flame"},
                ]
            },
            areas,
            {area_name_to_id(areas, "Kiln of the First Flame")},
            {
                **empty_state(),
                "bosses_defeated": [
                    "Abyss Watchers",
                    "Yhorm the Giant",
                    "Aldrich, Devourer of Gods",
                    "Dancer of the Boreal Valley",
                ],
            },
        ),
        "any requirement should succeed when one branch is met",
        failures,
    )


def test_get_accessible_items_formats(areas, locations, failures):
    sample_locations = {
        "multi_item": {
            "name": "Multi Item Test",
            "area": "Cemetery of Ash",
            "items": ["Long Sword", "Fist"],
            "source": "starting_equipment",
            "requires": None,
        },
    }

    items = get_accessible_items(areas, sample_locations, empty_state())
    assert_true(
        "Long Sword" in items and "Fist" in items,
        "get_accessible_items must support items arrays",
        failures,
    )
    assert_true(
        len(items) == len(set(items)),
        "get_accessible_items must not duplicate items from a single items array",
        failures,
    )

    single_location = {
        "single_item": {
            "name": "Single Item Test",
            "area": "Cemetery of Ash",
            "item": "Long Sword",
            "source": "starting_equipment",
            "requires": None,
        },
    }
    single_items = get_accessible_items(areas, single_location, empty_state())
    assert_true(
        single_items == ["Long Sword"],
        "get_accessible_items must support single item entries",
        failures,
    )


def test_progression_states(areas, failures):
    state1 = empty_state()
    assert_true(
        is_area_accessible(areas, state1, "Cemetery of Ash"),
        "STATE 1: Cemetery of Ash should be accessible for a new character",
        failures,
    )
    assert_true(
        not is_area_accessible(areas, state1, "Firelink Shrine"),
        "STATE 1: Firelink Shrine should not be accessible before Iudex Gundyr",
        failures,
    )

    state2 = empty_state()
    state2["bosses_defeated"] = ["Iudex Gundyr"]
    assert_true(
        is_area_accessible(areas, state2, "Firelink Shrine"),
        "STATE 2: Firelink Shrine should be accessible after Iudex Gundyr",
        failures,
    )
    assert_true(
        is_area_accessible(areas, state2, "High Wall of Lothric"),
        "STATE 2: High Wall of Lothric should be accessible after Iudex Gundyr",
        failures,
    )

    state3 = empty_state()
    state3["bosses_defeated"] = ["Iudex Gundyr", "Vordt of the Boreal Valley"]
    assert_true(
        is_area_accessible(areas, state3, "Undead Settlement"),
        "STATE 3: Undead Settlement should be accessible after Vordt",
        failures,
    )
    assert_true(
        is_area_accessible(areas, state3, "Road of Sacrifices"),
        "STATE 3: Road of Sacrifices should be reachable after Vordt",
        failures,
    )

    state4 = empty_state()
    state4["bosses_defeated"] = [
        "Iudex Gundyr",
        "Vordt of the Boreal Valley",
        "Abyss Watchers",
    ]
    assert_true(
        is_area_accessible(areas, state4, "Catacombs of Carthus"),
        "STATE 4: Catacombs of Carthus should be accessible after Abyss Watchers",
        failures,
    )

    state5 = empty_state()
    state5["bosses_defeated"] = [
        "Iudex Gundyr",
        "Vordt of the Boreal Valley",
        "Abyss Watchers",
        "High Lord Wolnir",
    ]
    assert_true(
        is_area_accessible(areas, state5, "Irithyll of the Boreal Valley"),
        "STATE 5: Irithyll of the Boreal Valley should be accessible after Wolnir",
        failures,
    )
    assert_true(
        is_area_accessible(areas, state5, "Irithyll Dungeon"),
        "STATE 5: Irithyll Dungeon should be accessible after Wolnir",
        failures,
    )
    assert_true(
        is_area_accessible(areas, state5, "Profaned Capital"),
        "STATE 5: Profaned Capital should be accessible after Wolnir",
        failures,
    )

    state6 = empty_state()
    state6["bosses_defeated"] = [
        "Iudex Gundyr",
        "Vordt of the Boreal Valley",
        "Abyss Watchers",
        "High Lord Wolnir",
        "Dancer of the Boreal Valley",
    ]
    assert_true(
        is_area_accessible(areas, state6, "Lothric Castle"),
        "STATE 6: Lothric Castle should be accessible after Dancer",
        failures,
    )
    assert_true(
        is_area_accessible(areas, state6, "Consumed King's Garden"),
        "STATE 6: Consumed King's Garden should be accessible after Dancer",
        failures,
    )
    assert_true(
        is_area_accessible(areas, state6, "Grand Archives"),
        "STATE 6: Grand Archives should be accessible after Dancer",
        failures,
    )

    state7 = empty_state()
    state7["bosses_defeated"] = [
        "Iudex Gundyr",
        "Vordt of the Boreal Valley",
        "Abyss Watchers",
        "High Lord Wolnir",
        "Dancer of the Boreal Valley",
        "Oceiros, the Consumed King",
    ]
    state7["gestures_obtained"] = ["Path of the Dragon"]
    assert_true(
        is_area_accessible(areas, state7, "Archdragon Peak"),
        "STATE 7: Archdragon Peak should be accessible with Oceiros and Path of the Dragon",
        failures,
    )
    assert_true(
        is_area_accessible(areas, state7, "Untended Graves"),
        "STATE 7: Untended Graves should be accessible after Oceiros",
        failures,
    )

    state8 = empty_state()
    state8["bosses_defeated"] = ["Sister Friede"]
    assert_true(
        is_area_accessible(areas, state8, "The Dreg Heap"),
        "STATE 8: The Dreg Heap should be accessible after Sister Friede",
        failures,
    )

    state9 = empty_state()
    state9["bosses_defeated"] = [
        "Abyss Watchers",
        "Yhorm the Giant",
        "Aldrich, Devourer of Gods",
        "Dancer of the Boreal Valley",
    ]
    assert_true(
        is_area_accessible(areas, state9, "Kiln of the First Flame"),
        "STATE 9: Kiln of the First Flame should be accessible after the four lords and Dancer",
        failures,
    )

    state10 = empty_state()
    state10["bosses_defeated"] = [
        "Abyss Watchers",
        "Yhorm the Giant",
        "Aldrich, Devourer of Gods",
        "Dancer of the Boreal Valley",
    ]
    assert_true(
        is_area_accessible(areas, state10, "Kiln of the First Flame"),
        "STATE 10: Kiln of the First Flame should be accessible",
        failures,
    )
    assert_true(
        is_area_accessible(areas, state10, "The Dreg Heap"),
        "STATE 10: The Dreg Heap should be accessible from Kiln without Sister Friede",
        failures,
    )


def test_item_access(areas, locations, failures):
    new_character_items = get_accessible_items(areas, locations, empty_state())
    assert_true(
        "Long Sword" in new_character_items,
        "Starting Long Sword should be available for a new character",
        failures,
    )

    firelink_state = empty_state()
    firelink_state["bosses_defeated"] = ["Iudex Gundyr"]
    firelink_items = get_accessible_items(areas, locations, firelink_state)
    assert_true(
        "Broken Straight Sword" in firelink_items,
        "Broken Straight Sword should be available once Firelink Shrine is accessible",
        failures,
    )

    high_wall_state = empty_state()
    high_wall_state["bosses_defeated"] = ["Iudex Gundyr"]
    high_wall_items = get_accessible_items(areas, locations, high_wall_state)
    assert_true(
        "Claymore" in high_wall_items,
        "High Wall weapons should become available once High Wall is accessible",
        failures,
    )

    catacombs_state = empty_state()
    catacombs_state["bosses_defeated"] = [
        "Iudex Gundyr",
        "Vordt of the Boreal Valley",
        "Abyss Watchers",
    ]
    catacombs_items = get_accessible_items(areas, locations, catacombs_state)
    assert_true(
        "Carthus Curved Sword" in catacombs_items,
        "Catacombs weapons should become available once Catacombs is accessible",
        failures,
    )

    smouldering_lake_state = empty_state()
    smouldering_lake_state["bosses_defeated"] = [
        "Iudex Gundyr",
        "Vordt of the Boreal Valley",
        "Abyss Watchers",
    ]
    smouldering_lake_items = get_accessible_items(
        areas, locations, smouldering_lake_state
    )
    assert_true(
        "Black Knight Sword" in smouldering_lake_items,
        "Smouldering Lake weapons should become available once Smouldering Lake is accessible",
        failures,
    )

    lothric_castle_state = empty_state()
    lothric_castle_state["bosses_defeated"] = [
        "Iudex Gundyr",
        "Vordt of the Boreal Valley",
        "Abyss Watchers",
        "High Lord Wolnir",
        "Dancer of the Boreal Valley",
    ]
    lothric_castle_items = get_accessible_items(
        areas, locations, lothric_castle_state
    )
    assert_true(
        "Lothric Knight Greatsword" in lothric_castle_items,
        "Lothric Knight Greatsword should be available once Lothric Castle is accessible",
        failures,
    )

    ringed_city_state = empty_state()
    ringed_city_state["bosses_defeated"] = ["Sister Friede"]
    ringed_city_items = get_accessible_items(areas, locations, ringed_city_state)
    assert_true(
        "Ringed Knight Paired Greatswords" in ringed_city_items,
        "Ringed Knight Paired Greatswords should be available once The Ringed City is accessible",
        failures,
    )

    full_items = get_accessible_items(areas, locations, ringed_city_state)
    assert_true(
        len(full_items) == len(set(full_items)),
        "get_accessible_items must not return duplicate weapons",
        failures,
    )


def test_randomizer(areas, locations, failures, base_dir="."):
    weapons = validate_database(base_dir)["weapons"]
    seed_a = 123456
    seed_b = 654321

    placements_a1 = randomize(seed_a, areas, weapons, locations)
    placements_a2 = randomize(seed_a, areas, weapons, locations)
    placements_b = randomize(seed_b, areas, weapons, locations)

    assert_true(
        placements_a1 == placements_a2,
        "Same seed should produce the same placement",
        failures,
    )
    assert_true(
        placements_a1 != placements_b,
        "Different seeds should produce different placements",
        failures,
    )

    assert_true(
        len(placements_a1) == len(locations),
        "Randomizer should assign one weapon to every location",
        failures,
    )

    assigned_weapons = []
    assigned_locations = set()
    for location_id, weapon_name in placements_a1.items():
        assigned_locations.add(location_id)
        if isinstance(weapon_name, list):
            assigned_weapons.extend(weapon_name)
        else:
            assigned_weapons.append(weapon_name)

    assert_true(
        len(assigned_locations) == len(locations),
        "No location should receive more than one placement",
        failures,
    )
    assert_true(
        len(assigned_weapons) == len(locations),
        "Exactly one weapon should be assigned per location",
        failures,
    )
    assert_true(
        len(assigned_weapons) == len(set(assigned_weapons)),
        "No weapon should be assigned more than once",
        failures,
    )

    weapon_names = {weapon["name"] for weapon in weapons}
    assert_true(
        set(assigned_weapons).issubset(weapon_names),
        "Every randomized weapon must exist in weapons.json",
        failures,
    )
    assert_true(
        set(placements_a1).issubset(set(locations.keys())),
        "Every randomized location must exist in locations.json",
        failures,
    )

    starting_ids = [
        location_id
        for location_id, location in locations.items()
        if location.get("source") == "starting_equipment"
    ]
    for location_id in starting_ids:
        original_weapon = locations[location_id].get("item")
        assigned_weapon = placements_a1.get(location_id)
        assert_true(
            original_weapon == assigned_weapon,
            "Starting equipment locations should preserve their original weapon",
            failures,
        )

    # Ensure original location metadata is unchanged.
    original_locations = {loc_id: dict(loc) for loc_id, loc in locations.items()}
    _ = randomize(seed_a, areas, weapons, locations)
    assert_true(
        locations == original_locations,
        "Randomizer should not modify original location metadata",
        failures,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        path = save_seed(placements_a1, seed_a, base_dir=temp_dir)
        loaded = load_seed(path)
        assert_true(
            loaded["seed"] == seed_a,
            "Saved seed file should preserve the seed",
            failures,
        )
        assert_true(
            loaded["placements"] == placements_a1,
            "Saved seed file should preserve placements",
            failures,
        )

    validation = validate_randomized_placement(
        placements_a1, areas, locations, seed=seed_a
    )
    assert_true(
        isinstance(validation, dict) and "valid" in validation,
        "Progression validator should execute and return structured results",
        failures,
    )


def run_tests(base_dir=None):
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    validation = validate_database(base_dir)
    failures = list(validation["errors"])
    areas = validation["areas"]
    locations = validation["locations"]

    test_requirement_met(areas, failures)
    test_get_accessible_items_formats(areas, locations, failures)
    test_progression_states(areas, failures)
    test_item_access(areas, locations, failures)
    test_randomizer(areas, locations, failures, base_dir=base_dir)

    return validation, failures


def print_demo(areas, locations):
    state = {
        "bosses_defeated": [
            "Iudex Gundyr",
            "Vordt of the Boreal Valley",
            "Crystal Sage",
            "Abyss Watchers",
        ],
        "areas_reached": [],
        "items_obtained": [],
        "gestures_obtained": [],
        "npcs_available": [],
    }

    accessible_items = get_accessible_items(areas, locations, state)

    print("Dark Souls 3 Randomizer")
    print()
    print("Currently obtainable items:")
    print()

    for item in accessible_items:
        print(item)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Dark Souls 3 weapon randomizer")
    parser.add_argument(
        "command",
        nargs="?",
        default="validate",
        choices=["validate", "randomize"],
        help="Action to run",
    )
    parser.add_argument("--seed", type=int, default=None, help="Deterministic seed")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    base_dir = os.path.dirname(os.path.abspath(__file__))

    if args.command == "randomize":
        try:
            result = generate_valid_seed(
                seed=args.seed,
                base_dir=base_dir,
                max_attempts=1000,
            )
        except (TypeError, ValueError) as exc:
            print(f"Randomization failed: {exc}")
            sys.exit(1)

        seed = result["seed"]
        placements = result["placements"]
        areas, weapons, locations = load_database(base_dir)
        validation = result["validation"]

        if not validation["valid"]:
            print("Generated seed did not satisfy validation requirements:")
            for reason in validation.get("reasons", []):
                print(f"  - {reason}")
            for reason in validation.get("progression_validation", {}).get("reasons", []):
                print(f"  - {reason}")
            sys.exit(1)

        output_path = save_randomizer_result(placements, seed, areas, weapons, locations, base_dir=base_dir)
        print(f"Randomization complete. Valid seed: {seed}")
        print(f"Saved output to: {output_path}")
        return 0

    validation, failures = run_tests(base_dir)

    print("Dark Souls 3 Randomizer - Validation Report")
    print("=" * 44)
    print(f"Weapons in weapons.json: {validation['weapon_count']}")
    print(f"Acquisition entries in locations.json: {validation['location_entry_count']}")
    print(
        "Every weapon has an acquisition entry: "
        + ("yes" if validation["all_weapons_have_locations"] else "no")
    )
    print(
        "Duplicate weapon names found: "
        + ("none" if not validation["duplicate_weapon_names"] else ", ".join(validation["duplicate_weapon_names"]))
    )
    print(
        "Duplicate JSON keys found: "
        + ("none" if not validation["duplicate_json_keys"] else ", ".join(validation["duplicate_json_keys"]))
    )
    print("JSON files parse correctly: yes")
    print("Python compilation succeeds: yes")
    print()

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        print()
        sys.exit(1)

    print("All progression and database checks passed.")
    print()
    print_demo(validation["areas"], validation["locations"])
    return 0


if __name__ == "__main__":
    main()
