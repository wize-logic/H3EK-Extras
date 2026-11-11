"""The example map's look: shaders per surface key, texture sizes, the light
material and its fixtures (what h3kit.ass needs), plus the scenario's cluster
data, so Avalanche's atmosphere and sounds reach the new level.

Shader names use collection prefixes (H3EK\\tags\\levels\\shader_collections.txt):
"side" = levels\\dlc\\sidewinder, "sb" = levels\\multi\\snowbound.
"""

import project
from h3kit import look as recipes
from h3kit.look import emissive

SHADERS = {
    "ground": "sb rock_rocky",              # packed grey gravel-rock with snowy detail
    "cliff": "sb rock_rocky",               # the same rock, side-projected on steep ground
    "sky": "+sky",
    "wall": "side side_basewall01",         # grey Forerunner panels
    "floor": "side side_basefloor02",
    "light": "side light_a",                # cyan-white light strip (emits, see LIGHTING)
}
GROUND_UV = 400.0      # repeats this large keep their UVs as they are (h3kit.ass.scale_uvs)
UV_REPEAT = {"ground": 6.0, "cliff": 6.0, "sky": GROUND_UV, "wall": 4.0, "floor": 4.0, "light": 2.0}
LIGHTING = {"light": emissive(20.0, (0.62, 0.86, 1.0), falloff=4.0, cutoff=12.0)}
# one generic light in front of each light strip: (intensity, reach)
FIXTURES = {"light": (12.6, 12.0)}

CLUSTER_RES = project.PROJECT.level_tag_dir("look\\example")
PER_CLUSTER = {   # block -> palette index for every cluster (-1 = none)
    "acoustics": 0,               # Avalanche's "exterior": outdoor reverb and wind
    "OLD background sounds": -1,
    "sound environments": -1,
    "weather properties": -1,
    "atmospheric properties": 0,  # Avalanche's snow atmosphere
    "camera fx properties": -1,
}


def tag_script():
    """mbedit lines: the cluster data for the new level (one sealed box: one cluster)."""
    return recipes.cluster_data_lines(project.PROJECT.base.resources, CLUSTER_RES, project.PROJECT.bsp, PER_CLUSTER)


def scenario_lines():
    return [f"set\tscenario resources[0]/new split resources[0]/cluster data resource\t"
            f"{CLUSTER_RES},scenario_cluster_data_resource",
            "set\tstructure bsps[0]/size class\t2048x2048"]
