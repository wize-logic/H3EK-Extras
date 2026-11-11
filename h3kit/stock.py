"""Stock Halo 3 tags a layout places by name: gameplay pieces (flags, spawns,
teleporters, hills, lifts, Forge blocks), vehicles, weapons and equipment,
with respawn times and the vehicles' resting heights.

Tags ported from other maps (donor.py) join VEHICLES, VEHICLE_REST and SUNK
when the project registers them, so a layout places them by name like any
stock vehicle.
"""

# team names in the scenario's "owner team" enum
RED, BLUE, NEUTRAL = "defender", "attacker", "neutral"

SAND = "objects\\levels\\dlc\\sandbox\\"
FORE = "objects\\levels\\dlc\\sidewinder\\"
PIECES = {  # name: (kind, tag); origins sit at the bottom centre of each piece
    "wall": ("crate", SAND + "sand_wallx2\\sand_wallx2"),            # 3.6 long (x), 1.8 tall
    "cube": ("crate", SAND + "sand_large_cube\\sand_large_cube"),    # 1.8 cube
    "cube2": ("crate", SAND + "sand_large_cubex2\\sand_large_cubex2"),  # 3.6 x 1.8 x 1.8
    "block": ("crate", SAND + "sand_block\\sand_block"),             # 1 cube
    "gatehouse": ("crate", SAND + "sand_gatehouse\\sand_gatehouse"),  # 1.4 x 1 x 3.1
    "bridge": ("crate", SAND + "sand_large_wood_bridge\\sand_large_wood_bridge"),  # 4.33 x 1.81, thin
    "scaffold": ("crate", SAND + "sand_scaffold\\sand_scaffold"),
    "column": ("crate", SAND + "sand_column_tt\\sand_column_tt"),    # 3.6 tall
    "fore_wall": ("crate", FORE + "fore_wall\\fore_wall"),           # 1.77 long (y), 1.8 tall
    "tower": ("crate", FORE + "tower_of_power\\tower_of_power"),     # 4.4 x 4.3 deck, 1.9 tall
    "man_cannon": ("crate", "objects\\levels\\dlc\\shared\\man_cannon_forge\\man_cannon_forge"),
    "flag": ("crate", "objects\\multi\\ctf\\ctf_flag_spawn_point"),
    "flag_return": ("crate", "objects\\multi\\ctf\\ctf_flag_return_area"),
    "teleporter": ("crate", "objects\\multi\\teleporter_2way\\teleporter_2way"),
    "respawn": ("scenery", "objects\\multi\\spawning\\respawn_point"),
    # the same respawn point without the Forge marker (stock Avalanche has a few)
    "respawn_invisible": ("scenery", "objects\\multi\\spawning\\respawn_point_invisible"),
    "initial": ("scenery", "objects\\multi\\ctf\\ctf_initial_spawn_point"),
    "respawn_zone": ("scenery", "objects\\multi\\ctf\\ctf_respawn_zone"),
    "hill": ("crate", "objects\\multi\\koth\\koth_hill_static"),          # the boundary is the hill
    "koth_initial": ("scenery", "objects\\multi\\koth\\koth_initial_spawn_point"),
    "slayer_initial": ("scenery", "objects\\multi\\slayer\\slayer_initial_spawn_point"),
    "infection_initial": ("scenery", "objects\\multi\\infection\\infection_initial_spawn_point"),
    "gravlift": ("equipment", "objects\\equipment\\gravlift_permanent\\gravlift_permanent"),
    # permanent lifts from stock maps (crates, no mv palette entry, phantom pushes from the physics model):
    # Construct's tall lift: straight up (marker up_lg) to about 8.4 above its origin, then out along +y
    "lift_tall": ("crate", "objects\\levels\\multi\\construct\\construct_lift_lg\\construct_lift_lg"),
    "lift_small": ("crate", "objects\\levels\\multi\\construct\\construct_lift_sm\\construct_lift_sm"),
    # Avalanche's own slanted lift: pushes along +y, 62 deg up, to about 4.5 above its origin
    "lift_ramp": ("crate", "objects\\levels\\dlc\\sidewinder\\lift_sidewinder\\lift_sidewinder"),
}
# each game type has its own initial spawn point tag (stock maps put one of each at every start);
# a start spot gets CTF's, King of the Hill's, Slayer's (all its variants, Fiesta too) and Infection's
INITIAL_PIECES = ("initial", "koth_initial", "slayer_initial", "infection_initial")
VEHICLES = {  # name: (tag, spawn seconds, forge display name)
    "elephant": ("objects\\levels\\multi\\shrine\\behemoth\\behemoth", 120, "elephant"),
    "scorpion": ("objects\\vehicles\\scorpion\\scorpion_snow", 90, "scorpion"),
    "wraith": ("objects\\vehicles\\wraith\\wraith", 90, "wraith"),
    "wraith_aa": ("objects\\vehicles\\wraith\\wraith_anti_air", 90, "wraith_anti_air"),
    "hornet": ("objects\\vehicles\\hornet\\hornet", 60, "hornet"),
    "banshee": ("objects\\vehicles\\banshee\\banshee", 60, "banshee"),
    "gauss": ("objects\\vehicles\\warthog\\warthog_gauss_snow", 45, "warthog_gauss"),
    "troop": ("objects\\vehicles\\warthog\\warthog_troop", 45, "warthog_troop"),
    "warthog": ("objects\\vehicles\\warthog\\warthog_snow", 45, "warthog"),
    "ghost": ("objects\\vehicles\\ghost\\ghost_snow", 30, "ghost"),
    "mongoose": ("objects\\vehicles\\mongoose\\mongoose_snow", 20, "mongoose"),
    "chopper": ("objects\\vehicles\\brute_chopper\\brute_chopper", 30, "brute_chopper"),
    "shade": ("objects\\vehicles\\shade\\shade", 60, "shade"),
}
# (origin height above the surface at rest, half length, half width) per vehicle,
# from each render model's bounds (the origin sits near the bottom; +0.03).
# Map vehicles are created with their physics asleep, so a vehicle placed
# any higher hangs in the air until something touches it.
VEHICLE_REST = {"elephant": (0.22, 4.2, 2.2), "scorpion": (0.14, 1.7, 1.3), "wraith": (0.0, 1.5, 1.5),
                "wraith_aa": (0.0, 1.5, 1.5), "hornet": (0.11, 1.6, 1.5), "banshee": (0.0, 1.0, 1.1),
                "gauss": (0.05, 1.0, 0.5), "troop": (0.05, 1.0, 0.5), "warthog": (0.05, 1.0, 0.5),
                "ghost": (0.2, 0.7, 0.6), "mongoose": (0.04, 0.5, 0.3), "chopper": (0.13, 1.1, 0.5),
                # the Shade: its render bounds reach down to the anti-gravity cone under its
                # base disc; resting that tip on a deck left the disc floating ~0.25.
                # 0.02: the disc on the deck, the cone below it out of sight
                "shade": (0.02, 0.7, 0.6)}
# rough footprint radii (from the measured sizes) for spacing and overlap tests
VEHICLE_RADIUS = {"elephant": 5.0, "scorpion": 2.1, "wraith": 2.1, "wraith_aa": 2.1, "hornet": 2.1,
                  "banshee": 1.5, "gauss": 1.2, "troop": 1.2, "warthog": 1.2, "ghost": 0.9,
                  "mongoose": 0.8, "chopper": 1.2, "shade": 1.0}
# fixed turrets whose model reaches below the origin (a pedestal): placed on the
# lowest ground under them rather than the highest
SUNK = set()


def vehicle_z(name, surface):
    """Where a vehicle's origin goes so it rests on a surface at height `surface`."""
    return surface + VEHICLE_REST.get(name, (0.05,))[0]


WEAPONS = {
    "br": ("objects\\weapons\\rifle\\battle_rifle\\battle_rifle", 15),
    "carbine": ("objects\\weapons\\rifle\\covenant_carbine\\covenant_carbine", 15),
    "ar": ("objects\\weapons\\rifle\\assault_rifle\\assault_rifle", 15),
    "sniper": ("objects\\weapons\\rifle\\sniper_rifle\\sniper_rifle", 60),
    "beam": ("objects\\weapons\\rifle\\beam_rifle\\beam_rifle", 60),
    "rocket": ("objects\\weapons\\support_high\\rocket_launcher\\rocket_launcher", 60),
    "laser": ("objects\\weapons\\support_high\\spartan_laser\\spartan_laser", 90),
    "flak": ("objects\\weapons\\support_high\\flak_cannon\\flak_cannon", 60),
    "shotgun": ("objects\\weapons\\rifle\\shotgun\\shotgun", 45),
    "sword": ("objects\\weapons\\melee\\energy_blade\\energy_blade", 60),
    "hammer": ("objects\\weapons\\melee\\gravity_hammer\\gravity_hammer", 60),
    "brute_shot": ("objects\\weapons\\support_low\\brute_shot\\brute_shot", 45),
    "sentinel": ("objects\\weapons\\support_low\\sentinel_gun\\sentinel_gun", 60),
    "missile_pod": ("objects\\weapons\\turret\\missile_pod\\missile_pod", 90),
    "plasma_cannon": ("objects\\weapons\\turret\\plasma_cannon\\plasma_cannon", 90),
    "flamethrower": ("objects\\weapons\\turret\\flamethrower\\flamethrower", 120),
}
EQUIPMENT = {
    "overshield": "objects\\multi\\powerups\\powerup_red\\powerup_red",
    "camo": "objects\\multi\\powerups\\powerup_blue\\powerup_blue",
    "bubble": "objects\\equipment\\bubbleshield_equipment\\bubbleshield_equipment",
    "regen": "objects\\equipment\\regenerator_equipment\\regenerator_equipment",
    "power_drain": "objects\\equipment\\powerdrain_equipment\\powerdrain_equipment",
    "trip_mine": "objects\\equipment\\tripmine_equipment\\tripmine_equipment",
    "grav_lift": "objects\\equipment\\gravlift_equipment\\gravlift_equipment",
    "cover": "objects\\equipment\\instantcover_equipment\\instantcover_equipment_mp",
    "flare": "objects\\equipment\\superflare_equipment\\superflare_equipment",
    # grenades lying on the map (off if the game variant turns map grenades off)
    "frag": "objects\\weapons\\grenade\\frag_grenade\\frag_grenade",
    "plasma_grenade": "objects\\weapons\\grenade\\plasma_grenade\\plasma_grenade",
    "spike_grenade": "objects\\weapons\\grenade\\claymore_grenade\\claymore_grenade",
    "firebomb": "objects\\weapons\\grenade\\firebomb_grenade\\firebomb_grenade",
}

# priority of a placement when a cap applies: lower numbers are kept first
MUST, GAMEPLAY, SCENERY, VEHICLE = 0, 1, 2, 3
PRIORITY = {"flag": MUST, "flag_return": MUST, "teleporter": MUST, "respawn": MUST, "respawn_invisible": MUST, "initial": MUST,
            "respawn_zone": MUST, "hill": MUST, "koth_initial": MUST, "slayer_initial": MUST,
            "infection_initial": MUST, "man_cannon": GAMEPLAY,
            "gravlift": GAMEPLAY,
            "lift_tall": GAMEPLAY, "lift_small": GAMEPLAY, "lift_ramp": GAMEPLAY}
