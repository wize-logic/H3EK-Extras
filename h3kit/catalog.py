"""Real Halo 3 props to dress a map with.

Every entry is a scenery or crate tag that ships in the Editing Kit (H3EK\\tags),
picked from Halo 3's multiplayer maps (Avalanche, Foundry, Standoff, Blackout,
Ghost Town, Sandbox, Orbital, Longshore, Icebox...) and campaign levels (The
Covenant's snowy pines, Halo's snowy boulders and Forerunner pillars, Tsavo
Highway's rocks and barriers...). Chosen to look right in snow, to collide, and
to need no scripts or AI.

Each entry carries the bounds of its render model (H3EK render_model
`render geometry/compression info`, x0, x1, y0, y1, z0, z1, world units, in the
object's own frame, read by an mbedit survey), whether its model has a
collision model, whether its object tag has a `multiplayer object` block (a
Forge-able item: it may count toward the 640-object map variant), and its
physics motion type.

Trees, logs, some barricades, masts and containers are campaign *crates*:
physics objects that a Warthog or a grenade could push over. They are listed
as static *scenery* wrappers (objects\\h3kit\\dressing\\<key>\\<key>.scenery,
WRAPPER_DIR), new tags whose only field is the original
model: same look and collision, never moves. `wraps` names the model and
`origin` the original object tag. wrapper_script() writes the mbedit commands
that (re)create them: run them once, before placing a wrapper
(ek.mbedit(catalog.wrapper_script(), "wrappers.txt")).

    python3 -m h3kit.catalog          # verify every tag exists, print the table

Bounds convention: z0 is where the object's lowest point is relative to its
origin (most props: 0, origin at the bottom; rocks and Forerunner pillars from
the campaign have their origin near mid-height, z0 < 0). Anything placing an
entry stands its lowest point on the ground with origin z = ground - z0.
"""

import math
import sys
from dataclasses import dataclass

from .env import EK

WRAPPER_DIR = "objects\\h3kit\\dressing"

CATEGORIES = {
    "tree": "pine trees (static scenery, trunk collision)",
    "log": "fallen logs and branches",
    "rock": "boulders, outcrops, rock slides",
    "forerunner": "Forerunner columns, walls, pillars, arches",
    "platform": "things to stand on: decks, ramps, scaffolds, plates, bridges",
    "unsc_cover": "UNSC barricades, jersey barriers, sandbags, walls, fences",
    "unsc_crate": "UNSC crates, containers, pallets, barrels",
    "unsc_gear": "UNSC antennas, towers, generators, flood lights, fuel, drop pods",
    "wreck": "crashed Pelican pieces, Hornet hulk, debris",
    "cov_cover": "Covenant barricades and emitters",
    "cov_crate": "Covenant supply crates",
    "cov_gear": "Covenant antennas, watchtower deck, ramp",
}


@dataclass(frozen=True)
class Entry:
    key: str
    tag: str             # path under H3EK\tags, no extension
    kind: str            # "scenery" or "crate" (scenario.KINDS key; also the tag extension)
    category: str
    bounds: tuple        # (x0, x1, y0, y1, z0, z1), object frame
    collision: bool      # its model has a collision_model
    mp: bool             # its object tag has a multiplayer object block (Forge item)
    source: str          # the map or level it comes from
    note: str
    plain: bool = False  # no attachments (lights, effects) and no object functions (animation): a plain
                         # static prop, convertible to a device_machine (which may not take a variant slot)
    motion: str = ""     # physics_model rigid body motion type(s): "fixed" never moves
    wraps: str = ""      # wrappers: the model this scenery tag points at
    origin: str = ""     # wrappers: the original object tag

    @property
    def size(self):
        x0, x1, y0, y1, z0, z1 = self.bounds
        return (x1 - x0, y1 - y0, z1 - z0)

    @property
    def height(self):
        return self.bounds[5] - self.bounds[4]

    @property
    def z0(self):
        """Lowest point relative to the origin (origin z = ground - z0)."""
        return self.bounds[4]

    @property
    def radius(self):
        """Footprint radius about the origin (x/y only)."""
        x0, x1, y0, y1 = self.bounds[:4]
        return math.hypot(max(-x0, x1), max(-y0, y1))

    @property
    def half(self):
        """Half extents (x, y) of the footprint about the origin."""
        x0, x1, y0, y1 = self.bounds[:4]
        return max(-x0, x1), max(-y0, y1)

    @property
    def long_x(self):
        """True if the footprint is longer along local x than y."""
        sx, sy, _ = self.size
        return sx >= sy

    @property
    def static(self):
        return self.kind == "scenery" or "fixed" == self.motion


E = Entry
ENTRIES = [
    E('pine_large', 'objects\\h3kit\\dressing\\pine_large\\pine_large', "scenery", 'tree', (-0.827, 0.74, -0.849, 1.044, -0.024, 4.042), True, False, 'The Covenant (100_citadel)', 'tall snowy pine, trunk collision', plain=True, wraps='objects\\levels\\solo\\100_citadel\\foliage\\plant_pine_tree_large\\plant_pine_tree_large', origin='objects\\levels\\solo\\100_citadel\\foliage\\plant_pine_tree_large\\plant_pine_tree_large'),
    E('pine', 'objects\\h3kit\\dressing\\pine\\pine', "scenery", 'tree', (-0.549, 0.496, -0.377, 0.522, -0.003, 2.572), True, False, 'The Covenant (100_citadel)', 'medium pine, trunk collision', plain=True, wraps='objects\\levels\\solo\\100_citadel\\foliage\\plant_tree_pine\\plant_tree_pine', origin='objects\\levels\\solo\\100_citadel\\foliage\\plant_tree_pine\\plant_tree_pine'),
    E('pine_twist', 'objects\\h3kit\\dressing\\pine_twist\\pine_twist', "scenery", 'tree', (-0.515, 0.561, -0.656, 0.294, -0.003, 2.562), True, False, 'The Covenant (100_citadel)', 'medium twisted pine', plain=True, wraps='objects\\levels\\solo\\100_citadel\\foliage\\plant_tree_pine_twist\\plant_tree_pine_twist', origin='objects\\levels\\solo\\100_citadel\\foliage\\plant_tree_pine_twist\\plant_tree_pine_twist'),
    E('log_split', 'objects\\h3kit\\dressing\\log_split\\log_split', "scenery", 'log', (-0.153, 0.257, -0.737, 0.664, 0.051, 0.273), True, False, 'The Covenant (100_citadel)', 'split fallen log, ankle cover', plain=True, wraps='objects\\levels\\solo\\100_citadel\\foliage\\tree_log_split\\tree_log_split', origin='objects\\levels\\solo\\100_citadel\\foliage\\tree_log_split\\tree_log_split'),
    E('log_thick', 'objects\\h3kit\\dressing\\log_thick\\log_thick', "scenery", 'log', (-0.242, 0.269, -1.186, 0.939, -0.04, 0.547), True, False, 'Sierra 117 (010_jungle)', 'thick fallen branch; jungle bark', plain=True, wraps='objects\\levels\\solo\\010_jungle\\foliage\\tree_branch_fallen_thick\\tree_branch_fallen_thick', origin='objects\\levels\\solo\\010_jungle\\foliage\\tree_branch_fallen_thick\\tree_branch_fallen_thick'),
    E('rock_big', 'objects\\levels\\solo\\030_outskirts\\scenery_rock\\scenery_rock', 'scenery', 'rock', (-5.389, 3.439, -4.361, 4.611, -2.645, 3.742), True, False, 'Tsavo Highway (030_outskirts)', 'huge outcrop, origin mid-height', plain=True, motion=''),
    E('rock_slide', 'objects\\levels\\solo\\120_halo\\rock_slide\\rock_slide\\rock_slide', 'scenery', 'rock', (-4.49, 3.629, -4.667, 3.557, -0.827, 4.043), True, False, 'Halo (120_halo)', 'snowy rock slide pile', plain=True, motion=''),
    E('boulder', 'objects\\levels\\solo\\120_halo\\boulder_med\\boulder_med', 'scenery', 'rock', (-2.628, 1.783, -2.682, 2.053, -2.55, 3.742), True, False, 'Halo (120_halo)', 'tall snowy boulder, origin mid-height', plain=True, motion=''),
    E('rock_flat', 'objects\\levels\\solo\\010_jungle\\rocks_large\\rock_a\\rock_a', 'scenery', 'rock', (-2.604, 2.615, -1.435, 1.435, -0.669, 0.669), True, False, 'Sierra 117 (010_jungle)', 'long low slab; may read slightly mossy', plain=True, motion=''),
    E('rock_small', 'objects\\h3kit\\dressing\\rock_small\\rock_small', "scenery", 'rock', (-0.627, 0.607, -0.675, 0.539, 0.307, 1.227), True, False, "Crow's Nest (020_base)", 'grey cave rock, chest high; origin under it', plain=True, wraps='objects\\levels\\solo\\020_base\\caverock_large\\caverock_large', origin='objects\\levels\\solo\\020_base\\caverock_large\\caverock_large'),
    E('fore_column_tall', 'objects\\levels\\dlc\\sandbox\\stone_column_tall\\stone_column_tall', 'crate', 'forerunner', (-0.335, 0.304, -0.433, 0.42, -0.004, 3.596), True, True, 'Sandbox', 'stone column 3.6 tall', plain=True, motion='fixed'),
    E('fore_column', 'objects\\levels\\dlc\\sandbox\\stone_column_short\\stone_column_short', 'crate', 'forerunner', (-0.307, 0.288, -0.414, 0.417, 0.002, 1.844), True, True, 'Sandbox', 'stone column 1.8 tall', plain=True, motion='fixed'),
    E('fore_column_broken', 'objects\\levels\\dlc\\sandbox\\stone_column_damaged\\stone_column_damaged', 'crate', 'forerunner', (-0.307, 0.291, -0.413, 0.417, 0.002, 1.489), True, True, 'Sandbox', 'broken stone column', plain=True, motion='box'),
    E('fore_column_tt', 'objects\\levels\\dlc\\sandbox\\sand_column_tt\\sand_column_tt', 'crate', 'forerunner', (-0.307, 0.286, -0.412, 0.415, 0.0, 3.592), True, True, 'Sandbox', 'tall sandbox column; made to slot into Sandbox walls (open faces in the open: unused since v1.1.0)', plain=True, motion='fixed'),
    E('fore_archtop', 'objects\\levels\\dlc\\sandbox\\sand_archtop\\sand_archtop', 'crate', 'forerunner', (-0.253, 0.246, -1.41, 1.659, 0.001, 0.771), True, True, 'Sandbox', 'arch lintel; in game it stands tilted, one end in the air, open faces (v1.1.0): do not use', plain=True, motion='fixed'),
    E('fore_wall', 'objects\\levels\\dlc\\sidewinder\\fore_wall\\fore_wall', 'crate', 'forerunner', (-0.038, 0.042, -0.886, 0.888, 0.0, 1.803), True, True, 'Avalanche (sidewinder)', 'Forerunner wall, 1.8 long (y) x 1.8 tall', plain=True, motion='fixed'),
    E('fore_wallcorner', 'objects\\levels\\dlc\\sidewinder\\fore_wallcorner\\fore_wallcorner', 'crate', 'forerunner', (-0.039, 1.689, -0.046, 1.682, 0.0, 1.803), True, True, 'Avalanche (sidewinder)', 'Forerunner corner wall', plain=True, motion='fixed'),
    E('fore_fightpos', 'objects\\levels\\dlc\\sidewinder\\fore_fightposition\\fore_fightposition', 'crate', 'forerunner', (-0.034, 0.615, -0.034, 0.616, -0.039, 0.482), True, True, 'Avalanche (sidewinder)', 'low Forerunner fighting position', plain=True, motion='fixed'),
    E('fore_ramp', 'objects\\levels\\dlc\\sidewinder\\fore_ramp\\fore_ramp', 'crate', 'platform', (-1.0, 1.0, -1.492, 2.497, 0.0, 1.467), True, True, 'Avalanche (sidewinder)', 'Forerunner ramp, rises 1.47 along +y', plain=True, motion='fixed'),
    E('fore_tower', 'objects\\levels\\dlc\\sidewinder\\tower_of_power\\tower_of_power', 'crate', 'platform', (-2.216, 2.21, -2.053, 2.213, -0.0, 1.904), True, True, 'Avalanche (sidewinder)', 'Avalanche tower deck 4.4 x 4.3 x 1.9', plain=True, motion='fixed'),
    E('fore_pillar', 'objects\\levels\\solo\\120_halo\\hallway_pillar\\hallway_pillar', 'scenery', 'forerunner', (-0.3, 0.3, -0.75, 0.96, -1.701, 1.706), True, False, 'Halo (120_halo)', 'ornate pillar 3.4 tall, origin mid-height', plain=True, motion='box'),
    E('fore_pillar_plain', 'objects\\levels\\solo\\120_halo\\hallway_pillar_basic\\hallway_pillar_basic', 'scenery', 'forerunner', (-0.5, 0.5, -1.15, 0.96, -1.675, 1.425), True, False, 'Halo (120_halo)', 'plain pillar 3.1 tall, origin mid-height', plain=True, motion='box'),
    E('fore_pillar_low', 'objects\\levels\\solo\\120_halo\\hall_trench_pillar\\hall_trench_pillar', 'scenery', 'forerunner', (-0.25, 0.25, -0.498, 0.378, -0.981, 0.704), True, False, 'Halo (120_halo)', 'short trench pillar, origin near top', plain=True, motion='box'),
    E('fore_shield_pillar', 'objects\\levels\\solo\\120_halo\\pillershield\\pillershield', 'scenery', 'forerunner', (-2.479, 2.387, -2.575, 2.435, -2.141, 0.414), True, False, 'Halo (120_halo)', 'big pillar base 4.9 x 5 x 2.6', plain=True, motion='box'),
    E('fore_plate', 'objects\\levels\\solo\\120_halo\\plates\\plate_flat\\plate_flat', 'crate', 'platform', (-3.777, 3.725, -3.775, 3.727, -0.072, 0.375), True, False, 'Halo (120_halo)', 'Forerunner floor plate 7.5 square', plain=False, motion='box'),
    E('fore_plate_ramp', 'objects\\levels\\solo\\120_halo\\plates\\plate_flat_ramp\\plate_flat_ramp', 'crate', 'platform', (-3.777, 3.725, -3.775, 3.727, -0.072, 1.894), True, False, 'Halo (120_halo)', 'plate with a ramp, 7.5 square, 2 tall', plain=True, motion='box'),
    E('fore_plate_corner', 'objects\\levels\\solo\\120_halo\\plates\\plate_corner_ramp\\plate_corner_ramp', 'crate', 'platform', (-3.742, 3.76, -3.762, 3.74, 0.175, 2.243), True, False, 'Halo (120_halo)', 'corner ramp plate', plain=True, motion='box'),
    E('barricade', 'objects\\h3kit\\dressing\\barricade\\barricade', "scenery", 'unsc_cover', (-0.316, 0.429, -0.678, 0.678, -0.061, 0.825), True, False, 'Valhalla/Forge (gear)', 'UNSC barricade, taller than a Spartan', plain=True, wraps='objects\\gear\\human\\military\\barricade_large\\barricade_large', origin='objects\\gear\\human\\military\\barricade_large\\barricade_large'),
    E('barricade_small', 'objects\\h3kit\\dressing\\barricade_small\\barricade_small', "scenery", 'unsc_cover', (-0.329, 0.294, -0.336, 0.336, -0.061, 0.825), True, False, 'Forge (gear)', 'short UNSC barricade', plain=True, wraps='objects\\gear\\human\\military\\barricade_small\\barricade_small', origin='objects\\gear\\human\\military\\barricade_small\\barricade_small'),
    E('jersey', 'objects\\gear\\human\\industrial\\jersey_barrier\\jersey_barrier', 'scenery', 'unsc_cover', (-0.241, 0.239, -0.703, 0.722, -0.002, 0.658), True, False, 'Tsavo Highway (gear)', 'concrete jersey barrier', plain=True, motion='box'),
    E('jersey_short', 'objects\\h3kit\\dressing\\jersey_short\\jersey_short', "scenery", 'unsc_cover', (-0.244, 0.236, -0.713, 0.712, -0.002, 0.524), True, False, 'Tsavo Highway (gear)', 'low jersey barrier', plain=True, wraps='objects\\gear\\human\\industrial\\jersey_barrier_short\\jersey_barrier_short', origin='objects\\gear\\human\\industrial\\jersey_barrier_short\\jersey_barrier_short'),
    E('sandbags', 'objects\\gear\\human\\military\\sandbag_wall\\sandbag_wall', 'scenery', 'unsc_cover', (-0.542, 0.561, -0.186, 0.253, -0.004, 0.403), True, False, 'campaign (gear)', 'sandbag wall 1.1 long (x)', plain=True, motion='box'),
    E('sandbags_45', 'objects\\gear\\human\\military\\sandbag_wall_45corner\\sandbag_wall_45corner', 'scenery', 'unsc_cover', (-0.471, 0.686, -0.22, 0.5, -0.013, 0.418), True, False, 'campaign (gear)', '45 degree sandbag corner', plain=True, motion='box'),
    E('sandbags_90', 'objects\\gear\\human\\military\\sandbag_wall_90corner\\sandbag_wall_90corner', 'scenery', 'unsc_cover', (-0.142, 0.729, -0.147, 0.695, -0.009, 0.379), True, False, 'campaign (gear)', '90 degree sandbag corner', plain=True, motion='box'),
    E('sandbags_end', 'objects\\gear\\human\\military\\sandbag_wall_endcap\\sandbag_wall_endcap', 'scenery', 'unsc_cover', (-0.212, 0.346, -0.194, 0.251, -0.002, 0.342), True, False, 'campaign (gear)', 'sandbag end cap', plain=True, motion='box'),
    E('sandbags_turret', 'objects\\gear\\human\\military\\sandbag_wall_turret\\sandbag_wall_turret', 'scenery', 'unsc_cover', (-0.547, 0.529, -0.15, 0.207, 0.002, 0.382), True, False, 'campaign (gear)', 'sandbag wall with turret notch', plain=True, motion='box'),
    E('concrete_block', 'objects\\levels\\dlc\\ghosttown\\ghosttown_block\\ghosttown_block', 'crate', 'unsc_cover', (-0.637, 0.614, -0.198, 0.197, -0.003, 0.482), True, True, 'Ghost Town', 'concrete block', plain=True, motion='fixed'),
    E('concrete_panel', 'objects\\levels\\dlc\\ghosttown\\ghosttown_panel\\ghosttown_panel', 'crate', 'unsc_cover', (-0.746, 0.777, -0.191, 0.354, -0.01, 2.075), True, True, 'Ghost Town', 'ruined wall panel 1.5 x 2.1', plain=True, motion='fixed'),
    E('rust_wall', 'objects\\levels\\dlc\\warehouse\\rustwalldouble\\rustwalldouble', 'crate', 'unsc_cover', (-0.144, 0.143, -1.797, 1.801, -0.0, 1.831), True, True, 'Foundry (warehouse)', 'rusty steel wall 3.6 long (y)', plain=True, motion='fixed'),
    E('rust_corner', 'objects\\levels\\dlc\\warehouse\\rustcorner\\rustcorner', 'crate', 'unsc_cover', (-0.145, 1.746, -0.146, 1.739, -0.004, 1.831), True, True, 'Foundry (warehouse)', 'rusty steel corner', plain=True, motion='fixed'),
    E('fence', 'objects\\levels\\dlc\\warehouse\\fencewall\\fencewall', 'crate', 'unsc_cover', (-0.217, 0.218, -0.899, 0.9, -0.001, 1.804), True, True, 'Foundry (warehouse)', 'chain-link fence 1.8 (y)', plain=True, motion='fixed'),
    E('wh_crate_large', 'objects\\levels\\dlc\\warehouse\\dlc_wh_crate_large_closed\\dlc_wh_crate_large_closed', 'crate', 'unsc_crate', (-1.78, 1.81, -0.882, 0.887, 0.002, 1.828), True, True, 'Foundry (warehouse)', 'big cargo crate 3.6 x 1.8 x 1.8', plain=True, motion='fixed'),
    E('wh_crate_long', 'objects\\levels\\dlc\\warehouse\\dlc_wh_crate_long_closed\\dlc_wh_crate_long_closed', 'crate', 'unsc_crate', (-1.849, 1.853, -0.908, 0.895, 0.0, 1.802), True, True, 'Foundry (warehouse)', 'long cargo crate', plain=True, motion='fixed'),
    E('wh_crate_short', 'objects\\levels\\dlc\\warehouse\\dlc_wh_crate_short_closed\\dlc_wh_crate_short_closed', 'crate', 'unsc_crate', (-0.858, 1.044, -0.901, 0.902, -0.007, 1.795), True, True, 'Foundry (warehouse)', 'short cargo crate', plain=True, motion='fixed'),
    E('wh_crate_cube', 'objects\\levels\\dlc\\warehouse\\dlc_wh_crate_small_closed\\dlc_wh_crate_small_closed', 'crate', 'unsc_crate', (-0.915, 0.915, -0.884, 0.885, 0.001, 1.824), True, True, 'Foundry (warehouse)', '1.8 cube crate', plain=True, motion='fixed'),
    E('wh_crate_open', 'objects\\levels\\dlc\\warehouse\\dlc_wh_crate_small_open\\dlc_wh_crate_small_open', 'crate', 'unsc_crate', (-0.915, 0.915, -0.884, 0.885, 0.001, 1.823), True, True, 'Foundry (warehouse)', '1.8 open crate', plain=True, motion='fixed'),
    E('semi', 'objects\\gear\\human\\industrial\\crate_tech_semi\\crate_tech_semi', 'scenery', 'unsc_crate', (-2.052, 2.055, -0.902, 0.901, -0.0, 1.8), True, False, 'campaign (gear)', 'semi-trailer container 4.1 long (x)', plain=True, motion='box'),
    E('semi_closed', 'objects\\gear\\human\\industrial\\crate_tech_semi_closed\\crate_tech_semi_closed', 'scenery', 'unsc_crate', (-2.052, 2.055, -0.908, 0.895, 0.0, 1.802), True, False, 'campaign (gear)', 'closed semi container', plain=True, motion='box'),
    E('semi_short', 'objects\\gear\\human\\industrial\\crate_tech_semi_short\\crate_tech_semi_short', 'scenery', 'unsc_crate', (-0.981, 1.016, -0.9, 0.903, -0.003, 1.797), True, False, 'campaign (gear)', 'short semi container 2 x 1.8', plain=True, motion='box'),
    E('semi_short_closed', 'objects\\gear\\human\\industrial\\crate_tech_semi_short_closed\\crate_tech_semi_short_closed', 'scenery', 'unsc_crate', (-0.976, 1.044, -0.901, 0.902, -0.007, 1.795), True, False, 'campaign (gear)', 'short closed container', plain=True, motion='box'),
    E('container_long', 'objects\\h3kit\\dressing\\container_long\\container_long', "scenery", 'unsc_crate', (-2.34, 2.171, -0.567, 0.567, -0.003, 1.164), True, False, 'Tsavo Highway (vehicles)', 'military container 4.5 long (x)', plain=True, wraps='objects\\vehicles\\civilian\\container_long_military\\container_long_military', origin='objects\\vehicles\\civilian\\container_long_military\\container_long_military'),
    E('container_small', 'objects\\h3kit\\dressing\\container_small\\container_small', "scenery", 'unsc_crate', (-1.504, 1.34, -0.569, 0.565, -0.022, 1.024), True, False, 'Tsavo Highway (vehicles)', 'small military container', plain=True, wraps='objects\\vehicles\\civilian\\container_small_military\\container_small_military', origin='objects\\vehicles\\civilian\\container_small_military\\container_small_military'),
    E('crate_multi', 'objects\\gear\\human\\industrial\\crate_multi\\crate_multi', 'scenery', 'unsc_crate', (-0.45, 0.45, -0.45, 0.45, -0.0, 0.9), True, False, 'campaign (gear)', 'stack of supply crates', plain=True, motion='box'),
    E('crate_single', 'objects\\gear\\human\\industrial\\crate_multi_single\\crate_multi_single', 'scenery', 'unsc_crate', (-0.226, 0.23, -0.23, 0.228, -0.001, 0.452), True, False, 'campaign (gear)', 'single supply crate', plain=True, motion='box'),
    E('crate_giant', 'objects\\gear\\human\\military\\crate_packing_giant\\crate_packing_giant', 'crate', 'unsc_crate', (-0.468, 0.468, -0.468, 0.468, 0.0, 0.899), True, True, 'campaign (gear)', 'large packing crate', plain=True, motion='box'),
    E('tarp_crates', 'objects\\gear\\human\\industrial\\tarp_crate_large_a\\tarp_crate_large_a', 'scenery', 'unsc_crate', (-0.566, 0.537, -0.569, 0.565, 0.0, 0.91), True, False, 'campaign (gear)', 'tarp-covered crates', plain=True, motion=''),
    E('tarp_crates_b', 'objects\\gear\\human\\industrial\\tarp_crate_large_b\\tarp_crate_large_b', 'scenery', 'unsc_crate', (-0.603, 0.631, -0.632, 0.556, 0.0, 0.928), True, False, 'campaign (gear)', 'tarp-covered crates', plain=True, motion=''),
    E('tarp_boxes', 'objects\\gear\\human\\industrial\\tarp_box_stack\\tarp_box_stack', 'scenery', 'unsc_crate', (-0.563, 0.573, -0.544, 0.57, -0.003, 0.857), True, False, 'campaign (gear)', 'tarp-covered box stack', plain=True, motion=''),
    E('pallet', 'objects\\gear\\human\\military\\pallet\\pallet', 'crate', 'unsc_crate', (-0.476, 0.46, -0.468, 0.468, 0.0, 0.114), True, True, 'campaign (gear)', 'military pallet', plain=True, motion='box'),
    E('water_barrels', 'objects\\levels\\dlc\\shared\\water_barrels\\water_barrels', 'crate', 'unsc_crate', (-0.449, 0.451, -0.461, 0.457, 0.0, 0.859), True, True, 'DLC shared', 'barrels on a pallet', plain=True, motion='box'),
    E('drum', 'objects\\gear\\human\\military\\drum_55gal\\drum_55gal', 'crate', 'unsc_crate', (-0.15, 0.15, -0.152, 0.152, 0.003, 0.458), True, True, 'campaign (gear)', '55 gallon drum', plain=False, motion='box'),
    E('barrel_rusty', 'objects\\levels\\dlc\\docks\\rusty_barrel\\barrel_rusty', 'scenery', 'unsc_crate', (-0.203, 0.203, -0.203, 0.203, 0.004, 0.651), True, False, 'Longshore (docks)', 'rusty barrel', plain=True, motion='box'),
    E('ammo_case', 'objects\\gear\\human\\military\\case_ap_turret\\case_ap_turret', 'crate', 'unsc_crate', (-0.504, 0.503, -0.29, 0.29, -0.003, 0.395), True, True, 'campaign (gear)', 'turret ammo case', plain=True, motion='box'),
    E('missile_stand', 'objects\\gear\\human\\military\\missle_stand\\missle_stand', 'scenery', 'unsc_gear', (-0.238, 0.233, -0.639, 0.588, 0.0, 0.559), True, False, 'campaign (gear)', 'missile on a cradle', plain=True, motion='box'),
    E('supply_pod', 'objects\\gear\\human\\military\\resupply_capsule_unfired\\resupply_capsule_unfired', 'crate', 'unsc_gear', (-0.141, 0.137, -0.137, 0.138, -0.151, 0.799), True, True, 'campaign (gear)', 'UNSC resupply drop pod (closed)', plain=False, motion='box'),
    E('supply_pod_open', 'objects\\gear\\human\\military\\resupply_capsule_fired\\resupply_capsule_fired', 'scenery', 'unsc_gear', (-0.141, 0.137, -0.137, 0.138, -0.114, 0.799), True, False, 'campaign (gear)', 'UNSC resupply drop pod (opened)', plain=False, motion='box'),
    E('hog_pallet', 'objects\\scenery\\human\\military\\warthog_drop_palette\\warthog_drop_palette', 'scenery', 'unsc_gear', (-1.405, 1.405, -0.685, 0.685, -0.015, 0.057), True, False, 'campaign (scenery)', 'Warthog drop pallet, flat', plain=True, motion='box'),
    E('antenna_mast', 'objects\\h3kit\\dressing\\antenna_mast\\antenna_mast', "scenery", 'unsc_gear', (-0.259, 0.269, -0.256, 0.256, -0.002, 4.016), True, False, 'campaign (gear)', '4 tall antenna mast', plain=True, wraps='objects\\gear\\human\\military\\antennae_mast\\antennae_mast', origin='objects\\gear\\human\\military\\antennae_mast\\antennae_mast'),
    E('radio_tower', 'objects\\levels\\dlc\\bunkerworld\\radio_tower\\radio_tower', 'scenery', 'unsc_gear', (-0.432, 0.441, -0.456, 0.456, -0.034, 4.977), True, False, 'Standoff (bunkerworld)', '5 tall radio tower', plain=True, motion='box'),
    E('celltower', 'objects\\levels\\dlc\\lockout\\celltower\\celltower', 'scenery', 'unsc_gear', (-0.595, 0.591, -0.556, 0.553, -0.053, 5.665), True, False, 'Blackout (lockout)', '5.7 tall comm tower', plain=True, motion='box'),
    E('celltower_simple', 'objects\\levels\\dlc\\lockout\\celltower_simple\\celltower_simple', 'scenery', 'unsc_gear', (-0.684, 0.594, -0.633, 0.529, -0.027, 4.274), True, False, 'Blackout (lockout)', '4.3 tall comm tower', plain=True, motion=''),
    E('windsock', 'objects\\levels\\dlc\\lockout\\windsock\\windsock', 'scenery', 'unsc_gear', (-0.367, 0.119, -0.189, 0.817, 0.005, 1.457), True, False, 'Blackout (lockout)', 'windsock on a pole', plain=True, motion='fixed'),
    E('windcups', 'objects\\levels\\dlc\\lockout\\windcups\\windcups', 'scenery', 'unsc_gear', (-0.282, 0.183, -0.248, 0.246, -0.0, 0.6), True, False, 'Blackout (lockout)', 'anemometer', plain=True, motion='box'),
    E('flood_light', 'objects\\gear\\human\\military\\generator_light\\generator_flood', 'crate', 'unsc_gear', (-0.31, 0.202, -0.207, 0.165, 0.006, 0.938), True, True, 'campaign (gear)', 'generator with flood lights (light attachments)', plain=False, motion='box'),
    E('generator', 'objects\\levels\\dlc\\spacecamp\\generator\\generator', 'crate', 'unsc_gear', (-0.302, 0.302, -0.285, 0.286, 0.0, 0.9), True, True, 'Orbital (spacecamp)', 'power generator', plain=True, motion='fixed'),
    E('old_generator', 'objects\\gear\\human\\industrial\\old_generator\\old_generator', 'scenery', 'unsc_gear', (-0.534, 0.556, -0.426, 0.404, -0.002, 1.128), True, False, 'campaign (gear)', 'old diesel generator; has an idle sound', plain=False, motion='box'),
    E('tarp_generator', 'objects\\gear\\human\\industrial\\tarp_old_generator\\tarp_old_generator', 'scenery', 'unsc_gear', (-0.726, 0.402, -0.456, 0.489, -0.007, 1.154), True, False, 'campaign (gear)', 'tarp-covered generator', plain=True, motion=''),
    E('generator_bulky', 'objects\\levels\\solo\\010_jungle\\dam_generator_bulky\\dam_generator_bulky', 'scenery', 'unsc_gear', (-0.614, 0.556, -0.5, 0.5, -0.0, 1.0), True, False, 'Sierra 117 (010_jungle)', 'bulky generator 1.2 x 1 x 1', plain=True, motion='box'),
    E('generator_kettle', 'objects\\levels\\solo\\010_jungle\\dam_generator_kettle\\dam_generator_kettle', 'scenery', 'unsc_gear', (-0.541, 0.541, -0.335, 0.335, 0.0, 1.171), True, False, 'Sierra 117 (010_jungle)', 'kettle generator', plain=True, motion='box'),
    E('fuel_tank', 'objects\\gear\\human\\industrial\\large_fuel_tank\\large_fuel_tank', 'scenery', 'unsc_gear', (-0.9, 0.9, -0.449, 0.449, 0.001, 0.899), True, False, 'campaign (gear)', 'large fuel tank on skids', plain=True, motion='box'),
    E('relay_box', 'objects\\levels\\solo\\010_jungle\\tech_control_substation_relay\\tech_control_substation_relay', 'scenery', 'unsc_gear', (-0.228, 0.255, -0.28, 0.28, 0.0, 1.062), True, False, 'Sierra 117 (010_jungle)', 'electrical relay cabinet', plain=True, motion='box'),
    E('systems_box', 'objects\\levels\\solo\\010_jungle\\tech_control_primary_systems_housing\\tech_control_primary_systems_housing', 'scenery', 'unsc_gear', (-0.228, 0.242, -0.187, 0.187, 0.0, 1.062), True, False, 'Sierra 117 (010_jungle)', 'systems cabinet', plain=True, motion='box'),
    E('scaffold', 'objects\\levels\\dlc\\sandbox\\sand_scaffold\\sand_scaffold', 'crate', 'platform', (-1.102, 1.12, -0.76, 0.753, -0.008, 2.119), True, True, 'Sandbox', 'standable scaffold 2.2 x 1.5 x 2.1', plain=True, motion='fixed'),
    E('gt_scaffold', 'objects\\levels\\dlc\\ghosttown\\ghosttown_scaffold\\ghosttown_scaffold', 'crate', 'platform', (-1.227, 1.187, -0.918, 0.888, -0.088, 2.801), True, True, 'Ghost Town', 'scaffold tower 2.9 tall', plain=True, motion='fixed'),
    E('gt_platform', 'objects\\levels\\dlc\\ghosttown\\ghosttown_platform\\ghosttown_platform', 'crate', 'platform', (-0.811, 0.811, -0.701, 0.701, -0.014, 0.148), True, True, 'Ghost Town', 'small platform deck', plain=True, motion='fixed'),
    E('wood_bridge', 'objects\\levels\\dlc\\sandbox\\sand_large_wood_bridge\\sand_large_wood_bridge', 'crate', 'platform', (-2.17, 2.159, -0.907, 0.898, -0.007, 0.099), True, True, 'Sandbox', 'wooden bridge plank 4.3 x 1.8', plain=True, motion='fixed'),
    E('stairs', 'objects\\levels\\dlc\\warehouse\\stairs\\stairs', 'crate', 'platform', (-1.513, 2.057, -0.529, 0.532, 0.004, 1.845), True, True, 'Foundry (warehouse)', 'steel stairs 3.6 long, 1.8 rise', plain=True, motion='fixed'),
    E('pelican_wreck', 'objects\\levels\\shared\\pelican_crashed_h3\\pelican_crashed_h3', 'scenery', 'wreck', (-4.947, 5.2, -3.879, 3.904, -0.274, 3.017), True, False, 'campaign shared', 'whole crashed Pelican 10 x 7.8 x 3.3', plain=False, motion='box'),
    E('pelican_hull', 'objects\\levels\\shared\\pelican_crashed_h3\\crash_hull\\crash_hull', 'scenery', 'wreck', (-4.596, 5.2, -1.838, 1.814, -1.384, 1.597), True, False, 'campaign shared', 'Pelican hull section, origin mid-height', plain=True, motion='box'),
    E('pelican_engine', 'objects\\levels\\shared\\pelican_crashed_h3\\crash_engine_lf_broken\\crash_engine_lf_broken', 'scenery', 'wreck', (-1.746, 0.973, -0.411, 1.688, -0.507, 1.142), True, False, 'campaign shared', 'broken Pelican engine pod', plain=True, motion='box'),
    E('pelican_wing', 'objects\\levels\\shared\\pelican_crashed_h3\\crash_engine_rf_wing_broken\\crash_engine_rf_wing_broken', 'scenery', 'wreck', (-0.861, 1.002, -0.841, 0.855, -0.307, 0.172), True, False, 'campaign shared', 'broken Pelican wing', plain=True, motion='box'),
    E('pelican_strut', 'objects\\levels\\shared\\pelican_crashed_h3\\crash_landing_strut_l\\crash_landing_strut_l', 'scenery', 'wreck', (-2.215, 0.349, -0.23, 0.793, -0.714, 0.462), True, False, 'campaign shared', 'Pelican landing strut', plain=True, motion='box'),
    E('hornet_wreck', 'objects\\levels\\multi\\s3d_turf\\turf_hornet\\turf_hornet', 'scenery', 'wreck', (-1.673, 1.47, -1.473, 1.439, -0.029, 1.459), True, False, 'Icebox (s3d_turf)', 'Hornet hulk', plain=False, motion='box'),
    E('truss_debris', 'objects\\levels\\solo\\030_outskirts\\tether_debris\\tether_debris_truss\\tether_debris_truss', 'crate', 'wreck', (-0.282, 0.216, -1.021, 1.048, 0.0, 1.202), True, False, 'Tsavo Highway (030_outskirts)', 'steel truss debris', plain=True, motion='box'),
    E('cov_barrier', 'objects\\h3kit\\dressing\\cov_barrier\\cov_barrier', "scenery", 'cov_cover', (-0.24, 0.16, -0.71, 0.71, -0.0, 0.788), True, False, 'campaign (gear)', 'Covenant barricade 1.4 wide (y)', plain=True, wraps='objects\\gear\\covenant\\military\\cov_barrier\\cov_barrier', origin='objects\\gear\\covenant\\military\\cov_barrier\\cov_barrier'),
    E('cov_emitter', 'objects\\gear\\covenant\\military\\cov_barrier_emitter\\cov_barrier_emitter', 'scenery', 'cov_cover', (-0.272, 0.537, -0.286, 0.295, 0.002, 0.665), True, False, 'campaign (gear)', 'Covenant shield emitter base', plain=False, motion=''),
    E('cov_crate', 'objects\\gear\\covenant\\military\\crate_space\\crate_space', 'crate', 'cov_crate', (-0.448, 0.448, -0.277, 0.27, -0.004, 0.919), True, True, 'campaign (gear)', 'Covenant supply crate', plain=True, motion='box'),
    E('cov_crate_a', 'objects\\gear\\covenant\\military\\crate_space_a\\crate_space_a', 'crate', 'cov_crate', (-0.448, 0.448, -0.274, 0.259, -0.004, 0.919), True, True, 'campaign (gear)', 'Covenant supply crate (lit)', plain=False, motion='box'),
    E('cov_crate_b', 'objects\\gear\\covenant\\military\\crate_space_b\\crate_space_b', 'crate', 'cov_crate', (-0.448, 0.448, -0.259, 0.26, -0.004, 0.919), True, True, 'campaign (gear)', 'Covenant supply crate (lit)', plain=False, motion='box'),
    E('cov_antenna', 'objects\\gear\\covenant\\military\\antennae_comm\\antennae_comm', 'crate', 'cov_gear', (-0.383, 0.383, -0.426, 0.264, -0.001, 3.068), True, True, 'campaign (gear)', 'Covenant comm antenna 3.1 tall, lights', plain=False, motion='box'),
    E('cov_tower_base', 'objects\\gear\\covenant\\military\\cov_watchtower\\cov_watchtower_base\\cov_watchtower_base', 'crate', 'cov_gear', (-1.317, 2.106, -1.893, 1.894, -0.28, 0.961), True, True, 'campaign (gear)', 'Covenant watchtower base deck 3.4 x 3.8', plain=False, motion='box'),
    E('cov_ramp', 'objects\\gear\\covenant\\military\\ramp\\ramp', 'crate', 'cov_gear', (-1.13, 0.844, -0.882, 0.882, -0.0, 0.937), True, True, 'campaign (gear)', 'Covenant boarding ramp 2 x 1.8 x 0.9', plain=True, motion='box'),
]
CATALOG = {e.key: e for e in ENTRIES}
assert len(CATALOG) == len(ENTRIES), "duplicate catalog keys"


def by_category(category):
    return [e for e in ENTRIES if e.category == category]


def wrapper_script():
    """mbedit commands that create the static scenery wrappers."""
    lines = []
    for e in ENTRIES:
        if e.wraps:
            lines += [f"new\t{e.tag}\tscenery",
                      f"set\tobject/model\t{e.wraps},model",
                      f"saveas\t{e.tag}\tscenery"]
    return lines


def verify(ek=EK):
    """Missing files: every tag (and each wrapper's model) must exist."""
    missing = []
    for e in ENTRIES:
        if not (ek / "tags" / f"{e.tag}.{e.kind}".replace("\\", "/")).exists():
            missing.append(f"{e.tag}.{e.kind}")
        if e.wraps and not (ek / "tags" / f"{e.wraps}.model".replace("\\", "/")).exists():
            missing.append(f"{e.wraps}.model")
    return missing


def table():
    rows = []
    for cat in CATEGORIES:
        es = by_category(cat)
        rows.append(f"{cat} ({len(es)}): {CATEGORIES[cat]}")
        for e in es:
            sx, sy, sz = e.size
            flags = ("coll " if e.collision else "nocoll ") + ("mp " if e.mp else "") + \
                    ("static" if e.static else "physics") + (" plain" if e.plain else "")
            rows.append(f"  {e.key:20s} {e.kind:7s} {sx:5.1f} x{sy:5.1f} x{sz:5.1f}  z0 {e.z0:+5.2f}  "
                        f"r {e.radius:4.1f}  {flags:24s} {e.source}: {e.note}")
    return "\n".join(rows)


def main():
    print(table())
    print(f"{len(ENTRIES)} entries, {sum(1 for e in ENTRIES if e.wraps)} static wrappers")
    if EK.exists():
        missing = verify()
        print("all tags present" if not missing else "MISSING:\n  " + "\n  ".join(missing))
        if missing:
            sys.exit(1)


if __name__ == "__main__":
    main()
