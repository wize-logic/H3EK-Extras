"""Stock multiplayer maps a new map can start from (project.BaseMap): what is
known about each scenario's leftovers once its level and placements go."""

from .project import BaseMap

# Avalanche (sidewinder): a snowy sky, Forerunner shaders, an MP game setup and Forge palettes
SIDEWINDER = BaseMap(
    scenario="levels\\dlc\\sidewinder\\sidewinder",
    resources="levels\\dlc\\sidewinder\\resources\\sidewinder",
    map_file="sidewinder.map",
    # trigger volumes renamed out of service (a "kill" or "safe_zone" name is what makes them work)
    # all its kill volumes: they fit Avalanche's old valley, and on a new level they cut through
    # the ground (kill_volumes_0 and _1 reach up from below the map: lower ground is inside them)
    retired_volumes={0: "open_valley_0", 1: "open_abyss_1", 2: "open_zone", 4: "open_edge_2",
                     5: "open_edge_3"},
    # objects its scenario still creates besides the placements (a build's object memory dumps and log)
    stock_objects=[("levels\\dlc\\sidewinder\\sky\\sky_sidewinder", "scenery", 1),   # exists before placement
                   ("sound\\levels\\dlc\\sidewinder\\sound_scenery\\sidewinder_cores\\sidewinder_cores",
                    "sound_scenery", 4),
                   ("sound\\levels\\dlc\\armory\\sound_scenery\\flourescent_light\\flourescent_light",
                    "sound_scenery", 17),
                   ("sound\\levels\\dlc\\sidewinder\\sound_scenery\\sidewinder_hologram\\sidewinder_holo_sputter",
                    "sound_scenery", 2),
                   ("sound\\levels\\dlc\\sidewinder\\sound_scenery\\sidewinder_hologram\\sidewinder_hologram",
                    "sound_scenery", 2),
                   ("levels\\dlc\\sidewinder\\fx\\steam_vent\\steam_vent", "effect_scenery", 4)],
)
# the stock vehicles and weapons sidewinder's Forge palette lacks (project.forge_vehicles / forge_weapons)
SIDEWINDER_FORGE_VEHICLES = ("elephant", "hornet", "gauss", "troop", "wraith_aa", "shade")
SIDEWINDER_FORGE_WEAPONS = ("plasma_cannon", "flamethrower")
