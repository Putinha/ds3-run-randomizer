import json
import os
import py_compile
import sys
from collections import Counter


VALID_SOURCES = {
    "starting_equipment",
    "corpse",
    "chest",
    "enemy_drop",
    "boss_drop",
    "boss_transposition",
    "npc_shop",
}

SPECIAL_AREAS = {"Starting Equipment"}


def load_json_no_duplicate_keys(path):
    with open(path, "r", encoding="utf-8") as file:
        text = file.read()

    duplicate_keys = []

    def object_pairs_hook(pairs):
        keys = [key for key, _ in pairs]
        seen = set()
        for key in keys:
            if key in seen:
                duplicate_keys.append(key)
            seen.add(key)
        return dict(pairs)

    data = json.loads(text, object_pairs_hook=object_pairs_hook)
    return data, duplicate_keys


def collect_requirements(requirement, result=None):
    if result is None:
        result = {
            "boss": set(),
            "area": set(),
            "item": set(),
            "gesture": set(),
            "npc": set(),
        }

    if requirement is None:
        return result

    if "all" in requirement:
        for item in requirement["all"]:
            collect_requirements(item, result)
    elif "any" in requirement:
        for item in requirement["any"]:
            collect_requirements(item, result)
    else:
        requirement_type = requirement.get("type")
        target = requirement.get("target")
        if requirement_type == "boss_defeated":
            result["boss"].add(target)
        elif requirement_type == "area_reached":
            result["area"].add(target)
        elif requirement_type == "item_obtained":
            result["item"].add(target)
        elif requirement_type == "gesture_obtained":
            result["gesture"].add(target)
        elif requirement_type == "npc_available":
            result["npc"].add(target)

    return result


def get_location_items(location):
    if "item" in location:
        return [location["item"]]
    if "items" in location:
        return list(location["items"])
    return []


def validate_database(base_dir="."):
    errors = []
    warnings = []

    areas_path = os.path.join(base_dir, "database", "areas.json")
    weapons_path = os.path.join(base_dir, "database", "weapons.json")
    locations_path = os.path.join(base_dir, "database", "locations.json")
    progression_path = os.path.join(base_dir, "engine", "progression.py")
    main_path = os.path.join(base_dir, "main.py")

    try:
        areas, area_dupes = load_json_no_duplicate_keys(areas_path)
    except json.JSONDecodeError as exc:
        return {"errors": [f"areas.json parse error: {exc}"], "warnings": []}

    try:
        weapons, weapon_dupes = load_json_no_duplicate_keys(weapons_path)
    except json.JSONDecodeError as exc:
        return {"errors": [f"weapons.json parse error: {exc}"], "warnings": []}

    try:
        locations, location_dupes = load_json_no_duplicate_keys(locations_path)
    except json.JSONDecodeError as exc:
        return {"errors": [f"locations.json parse error: {exc}"], "warnings": []}

    duplicate_json_keys = area_dupes + weapon_dupes + location_dupes

    for path in (progression_path, main_path):
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"Python compile error in {path}: {exc}")

    weapon_names = [weapon["name"] for weapon in weapons]
    weapon_name_set = set(weapon_names)
    duplicate_weapon_names = [
        name for name, count in Counter(weapon_names).items() if count > 1
    ]

    expected_weapon_fields = {"name", "type", "location", "progression", "dlc"}
    for weapon in weapons:
        missing_fields = expected_weapon_fields - set(weapon.keys())
        if missing_fields:
            errors.append(
                f"Weapon '{weapon.get('name', '?')}' missing fields: {sorted(missing_fields)}"
            )

    area_names = {area["name"] for area in areas.values()}
    all_bosses = set()
    all_gestures = set()
    all_items = set()
    all_npcs = set()

    for area in areas.values():
        requirements = collect_requirements(area.get("requires"))
        all_bosses.update(requirements["boss"])
        all_gestures.update(requirements["gesture"])
        all_items.update(requirements["item"])
        all_npcs.update(requirements["npc"])

    location_items = []
    weapons_in_locations = set()

    for location_id, location in locations.items():
        if "name" not in location:
            errors.append(f"Location '{location_id}' missing 'name'")
        if "area" not in location:
            errors.append(f"Location '{location_id}' missing 'area'")
        if "item" not in location and "items" not in location:
            errors.append(f"Location '{location_id}' missing 'item' or 'items'")
        if "source" not in location:
            errors.append(f"Location '{location_id}' missing 'source'")
        elif location["source"] not in VALID_SOURCES:
            errors.append(
                f"Location '{location_id}' has invalid source '{location['source']}'"
            )
        if "requires" not in location:
            errors.append(f"Location '{location_id}' missing 'requires'")

        area_name = location.get("area")
        if area_name and area_name not in area_names and area_name not in SPECIAL_AREAS:
            errors.append(
                f"Location '{location_id}' references unknown area '{area_name}'"
            )

        items = get_location_items(location)
        location_items.extend(items)
        weapons_in_locations.update(items)

        requirements = collect_requirements(location.get("requires"))
        all_bosses.update(requirements["boss"])
        all_gestures.update(requirements["gesture"])
        all_items.update(requirements["item"])
        all_npcs.update(requirements["npc"])

    weapons_missing_locations = sorted(weapon_name_set - weapons_in_locations)
    locations_missing_weapons = sorted(weapons_in_locations - weapon_name_set)

    if weapons_missing_locations:
        errors.append(
            "Weapons missing from locations.json: "
            + ", ".join(weapons_missing_locations)
        )

    if locations_missing_weapons:
        errors.append(
            "Location items missing from weapons.json: "
            + ", ".join(locations_missing_weapons)
        )

    referenced_areas = set()
    for area in areas.values():
        referenced_areas.update(
            collect_requirements(area.get("requires"))["area"]
        )
    for location in locations.values():
        referenced_areas.update(
            collect_requirements(location.get("requires"))["area"]
        )

    for area_name in referenced_areas:
        if area_name not in area_names:
            errors.append(f"Requirement references unknown area '{area_name}'")

    valid_bosses = set(all_bosses)
    valid_gestures = set(all_gestures)
    valid_items = set(all_items) | weapon_name_set
    valid_npcs = set(all_npcs)
    for location in locations.values():
        seller = location.get("seller")
        if seller:
            valid_npcs.add(seller)

    def validate_requirement_targets(requirement, context):
        if requirement is None:
            return
        if "all" in requirement:
            for item in requirement["all"]:
                validate_requirement_targets(item, context)
        elif "any" in requirement:
            for item in requirement["any"]:
                validate_requirement_targets(item, context)
        else:
            requirement_type = requirement.get("type")
            target = requirement.get("target")
            if requirement_type == "boss_defeated" and target not in valid_bosses:
                errors.append(
                    f"{context} references unknown boss '{target}'"
                )
            elif requirement_type == "area_reached" and target not in area_names:
                errors.append(
                    f"{context} references unknown area '{target}'"
                )
            elif requirement_type == "item_obtained" and target not in valid_items:
                errors.append(
                    f"{context} references unknown item '{target}'"
                )
            elif requirement_type == "gesture_obtained" and target not in valid_gestures:
                errors.append(
                    f"{context} references unknown gesture '{target}'"
                )
            elif requirement_type == "npc_available" and target not in valid_npcs:
                errors.append(
                    f"{context} references unknown NPC '{target}'"
                )

    for area_id, area in areas.items():
        validate_requirement_targets(
            area.get("requires"), f"Area '{area['name']}'"
        )

    for location_id, location in locations.items():
        validate_requirement_targets(
            location.get("requires"), f"Location '{location_id}'"
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "weapon_count": len(weapons),
        "location_entry_count": len(locations),
        "duplicate_weapon_names": duplicate_weapon_names,
        "duplicate_json_keys": duplicate_json_keys,
        "all_weapons_have_locations": len(weapons_missing_locations) == 0,
        "all_location_items_in_weapons": len(locations_missing_weapons) == 0,
        "areas": areas,
        "weapons": weapons,
        "locations": locations,
        "all_bosses": sorted(all_bosses),
        "all_gestures": sorted(all_gestures),
        "all_items": sorted(all_items),
        "all_npcs": sorted(all_npcs),
    }
