import json
import os
import random
from datetime import datetime

from engine.progression import get_accessible_areas, requirement_met

STARTING_EQUIPMENT_SOURCE = "starting_equipment"
MAX_PROGRESSION_TIER = 5


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_database(base_dir="."):
    areas_path = os.path.join(base_dir, "database", "areas.json")
    weapons_path = os.path.join(base_dir, "database", "weapons.json")
    locations_path = os.path.join(base_dir, "database", "locations.json")

    return (
        load_json(areas_path),
        load_json(weapons_path),
        load_json(locations_path),
    )


def get_starting_equipment_location_ids(locations):
    return sorted(
        loc_id
        for loc_id, loc in locations.items()
        if loc.get("source") == STARTING_EQUIPMENT_SOURCE
    )


def get_starting_equipment_weapon_names(locations):
    names = []
    for loc in locations.values():
        if loc.get("source") != STARTING_EQUIPMENT_SOURCE:
            continue
        if "item" in loc:
            names.append(loc["item"])
        elif "items" in loc:
            names.extend(loc["items"])
    return sorted(names)


def get_randomizable_location_ids(locations):
    return sorted(
        loc_id
        for loc_id, loc in locations.items()
        if loc.get("source") != STARTING_EQUIPMENT_SOURCE
    )


def get_randomizable_weapon_names(weapons, excluded_weapon_names):
    return sorted(
        weapon["name"]
        for weapon in weapons
        if weapon["name"] not in excluded_weapon_names
    )


def _normalize_seed(seed):
    if seed is None:
        return random.SystemRandom().randint(0, 2**32 - 1)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("Seed must be an integer")
    if seed < 0:
        raise ValueError("Seed must be non-negative")
    return seed


def _requirement_tier(requirement):
    if requirement is None:
        return 0
    if "all" in requirement:
        return max(_requirement_tier(item) for item in requirement["all"]) + 1
    if "any" in requirement:
        return max(_requirement_tier(item) for item in requirement["any"]) + 1

    requirement_type = requirement.get("type")
    if requirement_type == "boss_defeated":
        return 4
    if requirement_type == "area_reached":
        return 3
    if requirement_type in {"item_obtained", "gesture_obtained", "npc_available"}:
        return 2
    return 0


def _build_location_tiers(locations):
    tiers = {}
    late_areas = {
        "The Ringed City",
        "Kiln of the First Flame",
        "Archdragon Peak",
        "Irithyll of the Boreal Valley",
        "Anor Londo",
        "Lothric Castle",
        "Grand Archives",
    }
    for loc_id, location in locations.items():
        if location.get("source") == STARTING_EQUIPMENT_SOURCE:
            tiers[loc_id] = 0
            continue

        requirement_score = _requirement_tier(location.get("requires"))
        source_bonus = 0
        if location.get("source") in {"boss_drop", "boss_transposition"}:
            source_bonus = 2
        elif location.get("source") == "npc_shop":
            source_bonus = 1

        area_bonus = 2 if location.get("area") in late_areas else 0
        tier = max(1, min(MAX_PROGRESSION_TIER, requirement_score + source_bonus + area_bonus))
        tiers[loc_id] = tier

    return tiers


def randomize(seed, areas, weapons, locations):
    seed = _normalize_seed(seed)

    starting_equipment_location_ids = get_starting_equipment_location_ids(locations)
    starting_equipment_weapon_names = set(
        get_starting_equipment_weapon_names(locations)
    )

    randomizable_location_ids = get_randomizable_location_ids(locations)
    randomizable_weapon_names = get_randomizable_weapon_names(
        weapons, starting_equipment_weapon_names
    )

    if len(randomizable_location_ids) != len(randomizable_weapon_names):
        raise ValueError(
            "Randomization pool mismatch: "
            f"{len(randomizable_weapon_names)} weapons for "
            f"{len(randomizable_location_ids)} locations."
        )

    location_tiers = _build_location_tiers(locations)
    rng = random.Random(seed)
    placements = {}

    for loc_id in starting_equipment_location_ids:
        location = locations[loc_id]
        if "item" in location:
            placements[loc_id] = location["item"]
        elif "items" in location:
            placements[loc_id] = list(location["items"])
        else:
            placements[loc_id] = None

    remaining_weapons = [
        {"name": weapon["name"], "progression": weapon.get("progression", 1)}
        for weapon in weapons
        if weapon["name"] not in starting_equipment_weapon_names
    ]

    ordered_weapons = sorted(
        remaining_weapons,
        key=lambda weapon: (weapon["progression"], weapon["name"]),
        reverse=True,
    )
    remaining_locations = list(randomizable_location_ids)

    for weapon in ordered_weapons:
        tier = weapon["progression"]
        candidates = [
            loc_id
            for loc_id in remaining_locations
            if location_tiers.get(loc_id, 1) >= tier
        ]
        if not candidates:
            candidates = list(remaining_locations)
        if not candidates:
            raise ValueError(f"No location available for weapon {weapon['name']}")

        selected_location = candidates[rng.randrange(len(candidates))]
        placements[selected_location] = weapon["name"]
        remaining_locations.remove(selected_location)

    if len(placements) != len(locations):
        raise ValueError("Randomizer did not assign every location")

    return placements


def _needs_progression_item(requirement):
    if requirement is None:
        return False
    if "all" in requirement:
        return any(_needs_progression_item(item) for item in requirement["all"])
    if "any" in requirement:
        return any(_needs_progression_item(item) for item in requirement["any"])
    return requirement.get("type") in {
        "item_obtained",
        "gesture_obtained",
        "npc_available",
    }


def _collect_requirement_targets(requirement, target_types, output):
    """Collect fixed progression targets referenced by a requirement tree."""
    if requirement is None:
        return
    if "all" in requirement:
        for child in requirement["all"]:
            _collect_requirement_targets(child, target_types, output)
        return
    if "any" in requirement:
        for child in requirement["any"]:
            _collect_requirement_targets(child, target_types, output)
        return

    if requirement.get("type") in target_types:
        output.add(requirement.get("target"))


def _build_fixed_progression_state(areas, locations, state=None):
    """
    Build the state used to validate weapon placements.

    Bosses and gestures are fixed progression in this project; they are not
    randomized. Therefore validation may assume every fixed boss/gesture
    referenced by the database can eventually be completed/obtained.
    Randomized weapons, however, must still satisfy item_obtained requirements
    through the normal forward simulation.
    """
    state = state or {}
    active_state = {
        "bosses_defeated": list(state.get("bosses_defeated", [])),
        "areas_reached": list(state.get("areas_reached", [])),
        "items_obtained": list(state.get("items_obtained", [])),
        "gestures_obtained": list(state.get("gestures_obtained", [])),
        "npcs_available": list(state.get("npcs_available", [])),
    }

    bosses = set(active_state["bosses_defeated"])
    gestures = set(active_state["gestures_obtained"])
    npcs = set(active_state["npcs_available"])

    for data in list(areas.values()) + list(locations.values()):
        _collect_requirement_targets(
            data.get("requires"), {"boss_defeated"}, bosses
        )
        _collect_requirement_targets(
            data.get("requires"), {"gesture_obtained"}, gestures
        )
        _collect_requirement_targets(
            data.get("requires"), {"npc_available"}, npcs
        )

    active_state["bosses_defeated"] = sorted(bosses)
    active_state["gestures_obtained"] = sorted(gestures)
    active_state["npcs_available"] = sorted(npcs)
    return active_state


def validate_randomized_placement(
    placements,
    areas,
    locations,
    state=None,
    seed=None,
):
    active_state = _build_fixed_progression_state(areas, locations, state)

    reachable_areas = get_accessible_areas(areas, active_state)
    reachable_area_names = {areas[area_id]["name"] for area_id in reachable_areas}

    obtained_items = set(active_state["items_obtained"])
    reachable_locations = set()

    # Forward-chain randomized item requirements. A location can be opened
    # only when its area and its own requirements are satisfied. Its assigned
    # weapon then becomes an obtained item and may unlock another location.
    changed = True
    while changed:
        changed = False
        simulation_state = {
            **active_state,
            "items_obtained": sorted(obtained_items),
        }

        for location_id, location in locations.items():
            if location_id in reachable_locations:
                continue
            if location.get("area") not in reachable_area_names:
                continue
            if not requirement_met(
                location.get("requires"),
                areas,
                reachable_areas,
                simulation_state,
            ):
                continue

            assigned_weapon = placements.get(location_id)
            if assigned_weapon is None:
                continue

            reachable_locations.add(location_id)
            if isinstance(assigned_weapon, list):
                new_items = set(assigned_weapon) - obtained_items
            else:
                new_items = {assigned_weapon} - obtained_items

            if new_items:
                obtained_items.update(new_items)
                changed = True

        if changed:
            simulation_state["items_obtained"] = sorted(obtained_items)
            reachable_areas = get_accessible_areas(areas, simulation_state)
            reachable_area_names = {
                areas[area_id]["name"] for area_id in reachable_areas
            }

    unreachable_locations = [
        location_id
        for location_id in locations
        if location_id not in reachable_locations
    ]

    blocked_locations = []
    for location_id in unreachable_locations:
        location = locations[location_id]
        if location.get("area") not in reachable_area_names:
            continue
        if _needs_progression_item(location.get("requires")):
            blocked_locations.append(location_id)

    valid = not unreachable_locations and not blocked_locations

    reasons = []
    if unreachable_locations:
        reasons.append(
            "Unreachable locations: " + ", ".join(sorted(unreachable_locations))
        )
    if blocked_locations:
        reasons.append(
            "Progression-blocked locations: " + ", ".join(sorted(blocked_locations))
        )

    return {
        "valid": valid,
        "seed": seed,
        "reachable_areas": sorted(reachable_area_names),
        "reachable_locations": sorted(reachable_locations),
        "reachable_items": sorted(obtained_items),
        "unreachable_locations": sorted(unreachable_locations),
        "blocked_locations": sorted(blocked_locations),
        "reasons": reasons,
    }

def validate_randomizer_output(placements, areas, weapons, locations, seed=None):
    weapon_names = {weapon["name"] for weapon in weapons}
    assigned_weapons = []
    invalid_reasons = []

    if len(placements) != len(locations):
        invalid_reasons.append("Placement count does not match the number of locations")

    for location_id, assigned_weapon in placements.items():
        if location_id not in locations:
            invalid_reasons.append(f"Unknown location '{location_id}'")
            continue

        location = locations[location_id]
        if isinstance(assigned_weapon, list):
            assigned_weapons.extend(assigned_weapon)
        else:
            assigned_weapons.append(assigned_weapon)

        if location.get("source") == STARTING_EQUIPMENT_SOURCE:
            expected_weapon = location.get("item")
            if expected_weapon is not None and assigned_weapon != expected_weapon:
                invalid_reasons.append(
                    f"Starting equipment '{location_id}' should preserve its original weapon"
                )

    if len(assigned_weapons) != len(weapon_names):
        invalid_reasons.append("Assigned weapon count does not match the weapon database")

    if len(set(assigned_weapons)) != len(assigned_weapons):
        invalid_reasons.append("Weapons are duplicated across placements")

    if set(assigned_weapons) != weapon_names:
        invalid_reasons.append("Assigned weapons do not match the full weapon database")

    if any(weapon not in weapon_names for weapon in assigned_weapons if weapon is not None):
        invalid_reasons.append("Assigned weapon names are not present in weapons.json")

    progression_validation = validate_randomized_placement(
        placements,
        areas,
        locations,
        seed=seed,
    )

    return {
        "valid": not invalid_reasons and progression_validation["valid"],
        "seed": seed,
        "reasons": invalid_reasons,
        "progression_validation": progression_validation,
    }


def generate_valid_seed(seed=None, base_dir=".", max_attempts=1000):
    areas, weapons, locations = load_database(base_dir)
    start_seed = seed if seed is not None else random.SystemRandom().randint(0, 2**32 - 1)
    candidate = start_seed

    for attempt in range(max_attempts):
        placements = randomize(candidate, areas, weapons, locations)
        validation = validate_randomizer_output(
            placements,
            areas,
            weapons,
            locations,
            seed=candidate,
        )
        if validation["valid"]:
            return {
                "seed": candidate,
                "placements": placements,
                "validation": validation,
            }
        candidate += 1

    raise ValueError(
        f"No valid seed found within {max_attempts} attempts starting from {start_seed}."
    )


def save_seed(placements, seed, base_dir=".", filename=None):
    output_dir = os.path.join(base_dir, "output", "seeds")
    os.makedirs(output_dir, exist_ok=True)

    if filename is None:
        filename = f"seed_{seed}.json"

    if not filename.lower().endswith(".json"):
        filename += ".json"

    path = os.path.join(output_dir, filename)
    base_name, extension = os.path.splitext(filename)
    attempt = 1
    while os.path.exists(path):
        path = os.path.join(output_dir, f"{base_name}_{attempt}{extension}")
        attempt += 1

    data = {
        "seed": seed,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "placements": placements,
    }

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    return path


def build_randomizer_output(placements, areas, weapons, locations, seed=None):
    rows = []
    for location_id in sorted(locations):
        location = locations[location_id]
        rows.append(
            {
                "location_id": location_id,
                "acquisition_location": location.get("name"),
                "area": location.get("area"),
                "source": location.get("source"),
                "original_weapon": location.get("item") or location.get("items"),
                "randomized_weapon": placements.get(location_id),
                "requires": location.get("requires"),
            }
        )

    return {
        "seed": seed,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "weapon_count": len(weapons),
        "location_count": len(locations),
        "assignments": rows,
    }


def save_randomizer_result(placements, seed, areas, weapons, locations, base_dir=".", filename=None):
    output_dir = os.path.join(base_dir, "output", "randomizer_results")
    os.makedirs(output_dir, exist_ok=True)

    if filename is None:
        filename = f"seed_{seed}.json"
    if not filename.lower().endswith(".json"):
        filename += ".json"

    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            build_randomizer_output(placements, areas, weapons, locations, seed=seed),
            file,
            indent=2,
            ensure_ascii=False,
        )

    return path


def load_seed(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def format_placement_summary(placements, locations, limit=10):
    rows = []
    for location_id, weapon_name in placements.items():
        location_name = locations[location_id]["name"]
        rows.append((location_name, weapon_name))
    rows.sort()

    summary = [f"{weapon_name} -> {location_name}" for location_name, weapon_name in rows[:limit]]
    if len(rows) > limit:
        summary.append(f"...and {len(rows) - limit} more placements")
    return summary
