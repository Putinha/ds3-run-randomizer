def requirement_met(requirement, areas, accessible_areas, state):
    if requirement is None:
        return True

    if "all" in requirement:
        return all(
            requirement_met(item, areas, accessible_areas, state)
            for item in requirement["all"]
        )

    if "any" in requirement:
        return any(
            requirement_met(item, areas, accessible_areas, state)
            for item in requirement["any"]
        )

    requirement_type = requirement["type"]
    target = requirement["target"]

    if requirement_type == "boss_defeated":
        return target in state.get("bosses_defeated", [])

    if requirement_type == "area_reached":
        target_area_id = next(
            (
                area_id
                for area_id, area in areas.items()
                if area["name"] == target
            ),
            None
        )

        return target_area_id in accessible_areas

    if requirement_type == "item_obtained":
        return target in state.get("items_obtained", [])

    if requirement_type == "gesture_obtained":
        return target in state.get("gestures_obtained", [])

    if requirement_type == "npc_available":
        return requirement["target"] in state.get("npcs_available", [])

    return False


def get_accessible_areas(areas, state):
    accessible_areas = set()

    changed = True

    while changed:
        changed = False

        for area_id, area in areas.items():
            if area_id in accessible_areas:
                continue

            if requirement_met(
                area["requires"],
                areas,
                accessible_areas,
                state
            ):
                accessible_areas.add(area_id)
                changed = True

    return accessible_areas


def get_accessible_items(areas, locations, state):
    accessible_areas = get_accessible_areas(areas, state)

    accessible_area_names = {
        areas[area_id]["name"]
        for area_id in accessible_areas
    }

    accessible_items = []

    for location in locations.values():
        if location["area"] not in accessible_area_names:
            continue

        if not requirement_met(
            location["requires"],
            areas,
            accessible_areas,
            state
        ):
            continue

        if "item" in location:
            accessible_items.append(location["item"])

        elif "items" in location:
            accessible_items.extend(location["items"])

    return accessible_items