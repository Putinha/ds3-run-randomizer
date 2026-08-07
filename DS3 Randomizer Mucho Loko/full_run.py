"""Full-run build generator for the DS3 randomizer."""

import json
import os
import random


STARTING_EQUIPMENT_SOURCE = "starting_equipment"


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_full_run_database(base_dir="."):
    database_dir = os.path.join(base_dir, "database")

    return {
        "areas": load_json(
            os.path.join(database_dir, "areas.json")
        ),
        "weapons": load_json(
            os.path.join(database_dir, "weapons.json")
        ),
        "locations": load_json(
            os.path.join(database_dir, "locations.json")
        ),
        "spells": load_json(
            os.path.join(database_dir, "spells.json")
        ),
        "catalysts": load_json(
            os.path.join(database_dir, "catalysts.json")
        ),
        "shields": load_json(
            os.path.join(database_dir, "shields.json")
        ),
        "rings": load_json(
            os.path.join(database_dir, "rings.json")
        ),
        "build_rules": load_json(
            os.path.join(database_dir, "build_rules.json")
        ),
    }


def get_weapon_name(weapon):
    if isinstance(weapon, str):
        return weapon

    return weapon["name"]


def get_starting_weapons(locations):
    starting_weapons = []

    for location in locations.values():

        if location.get("source") != STARTING_EQUIPMENT_SOURCE:
            continue

        if "item" in location:
            starting_weapons.append(location["item"])

        elif "items" in location:
            starting_weapons.extend(location["items"])

    return sorted(set(starting_weapons))


def get_all_weapon_names(weapons):
    return sorted(
        {
            get_weapon_name(weapon)
            for weapon in weapons
        }
    )


def get_magic_catalyst_pool(spells, catalysts):
    catalyst_types = {
        catalyst["type"]
        for catalyst in catalysts
    }

    valid_spells = [
        spell
        for spell in spells
        if spell.get("catalyst_type") in catalyst_types
    ]

    return valid_spells


def choose_magic(rng, spells, catalysts):
    """
    Magic is optional.

    Returns:
        {
            "spell": ...,
            "catalyst": ...
        }

    or:

        {
            "spell": None,
            "catalyst": None
        }
    """

    if not spells:
        return {
            "spell": None,
            "catalyst": None,
        }

    # 50% chance of receiving a magic.
    if rng.random() >= 0.5:
        return {
            "spell": None,
            "catalyst": None,
        }

    valid_spells = get_magic_catalyst_pool(
        spells,
        catalysts
    )

    if not valid_spells:
        return {
            "spell": None,
            "catalyst": None,
        }

    spell = rng.choice(valid_spells)

    valid_catalysts = [
        catalyst
        for catalyst in catalysts
        if catalyst["type"] == spell["catalyst_type"]
    ]

    catalyst = rng.choice(valid_catalysts)

    return {
        "spell": spell["name"],
        "school": spell["school"],
        "catalyst": catalyst["name"],
    }


def choose_shield(rng, shields):
    """
    Shield is optional.
    """

    if not shields:
        return None

    # 50% chance of receiving a shield.
    if rng.random() >= 0.5:
        return None

    return rng.choice(shields)["name"]


def choose_rings(rng, rings):
    """
    Exactly four different rings are always generated.
    """

    if len(rings) < 4:
        raise ValueError(
            "At least four rings are required."
        )

    selected = rng.sample(rings, 4)

    return [
        ring["name"]
        for ring in selected
    ]


def choose_build(rng, build_rules):
    final_level_rules = build_rules["final_level"]

    min_level = 50
    max_level = 180

    if min_level > max_level:
        raise ValueError(
            "build_rules.json has an invalid final level range."
        )

    final_level = rng.randint(
        min_level,
        max_level
    )

    stats = list(build_rules["stats"])

    if not stats:
        raise ValueError(
            "build_rules.json contains no stats."
        )

    priority_rules = build_rules["priority_count"]

    min_priority = int(priority_rules["min"])
    max_priority = int(priority_rules["max"])

    max_priority = min(
        max_priority,
        len(stats)
    )

    min_priority = min(
        min_priority,
        max_priority
    )

    priority_count = rng.randint(
        min_priority,
        max_priority
    )

    priorities = rng.sample(
        stats,
        priority_count
    )

    return {
    "final_level": final_level,
}


def generate_full_run(seed=None, base_dir="."):
    database = load_full_run_database(base_dir)

    areas = database["areas"]
    weapons = database["weapons"]
    locations = database["locations"]
    spells = database["spells"]
    catalysts = database["catalysts"]
    shields = database["shields"]
    rings = database["rings"]
    build_rules = database["build_rules"]

    del areas

    if seed is None:
        seed = random.SystemRandom().randint(
            0,
            2**32 - 1
        )

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(
            "Seed must be an integer."
        )

    if seed < 0:
        raise ValueError(
            "Seed must be non-negative."
        )

    rng = random.Random(seed)

    starting_weapons = get_starting_weapons(
        locations
    )

    all_weapons = get_all_weapon_names(
        weapons
    )

    if not starting_weapons:
        raise ValueError(
            "No starting weapons were found."
        )

    if len(all_weapons) < 3:
        raise ValueError(
            "At least three weapons are required."
        )

# -------------------------------------------------
# STARTING CLASS + FINAL WEAPON
# -------------------------------------------------

    starting_classes = [
        "Knight",
        "Mercenary",
        "Warrior",
        "Herald",
        "Thief",
        "Assassin",
        "Sorcerer",
        "Pyromancer",
        "Cleric",
        "Deprived",
]

    starting_class = rng.choice(starting_classes)

    final_weapon = rng.choice(all_weapons)

    # -------------------------------------------------
    # OPTIONAL MAGIC + CATALYST
    # -------------------------------------------------

    magic = choose_magic(
        rng,
        spells,
        catalysts
    )

    # -------------------------------------------------
    # OPTIONAL SHIELD
    # -------------------------------------------------

    shield = choose_shield(
        rng,
        shields
    )

    # -------------------------------------------------
    # FOUR MANDATORY RINGS
    # -------------------------------------------------

    selected_rings = choose_rings(
        rng,
        rings
    )

    # -------------------------------------------------
    # CHARACTER BUILD
    # -------------------------------------------------

    build = choose_build(
        rng,
        build_rules
    )

    return {
        "seed": seed,

        "weapons": {
            "starting_class": starting_class,
            "weapon": final_weapon,
        },

        "magic": magic,

        "shield": shield,

        "rings": selected_rings,

        "character": build,
    }


if __name__ == "__main__":
    result = generate_full_run()

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )
