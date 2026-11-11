"""How a level looks: emissive materials for the .ASS, and the mbedit recipes
that give a new level its own copies of a stock map's sky, atmosphere,
terrain shaders and cluster data.

A map's own look module holds its choices (SHADERS, UV_REPEAT, GROUND_UV,
LIGHTING, FIXTURES: see ass.py) and calls these recipes with them.

Shader names. "<collection prefix> <shader>" (prefixes in H3EK\\tags\\levels\\
shader_collections.txt, e.g. "side" = levels\\dlc\\sidewinder, "sb" =
levels\\multi\\snowbound; tool looks only in the collection's own shaders\\
folder, not in its sub-folders), a name with no prefix (tool looks in the
level's own shaders folder, tags\\<level>\\shaders) or a special material
("+sky"). Shaders a prefix can't reach are copied into the level's own
shaders folder (terrain_shader_lines) before tool structure runs.

Light. emissive() gives a light material the .ASS emissive strings (the
format the Halo Asset Blender toolset writes, file_ass/process_scene.py
get_material_strings, ASS version >= 4): tool copies them into the level's
structure lighting info ("material info"), and the lightmapper makes a
"surface light" of every face with that material. Distances in the strings
are .ASS units (world units x 100): tool divides them by 100. A panel's
emissive light barely reaches the floor below it, so rooms need generic
lights too (lights.py, one per fixture).
"""


def emissive(power, color, falloff, cutoff, per_area=True, focus=0.0, quality=1.0, res=1.0):
    """The five .ASS lighting strings for a light-giving material.

    power: emissive power (per square world unit when per_area, else for all
    faces of the material together, split between them); color: 0..1 rgb;
    light fades from `falloff` to nothing at `cutoff` world units (written
    x 100 for the .ASS); focus 0
    spreads light over the hemisphere, 1 aims it straight out of the face.
    Bungie's Avalanche lights (its BSP lighting info) use power 2-40, quality 1,
    falloff 1-10 and cutoff 3-20, frustum angles 25/45."""
    r, g, b = color
    return [
        "BM_FLAGS " + "0" * 22,      # two-sided, transparent ... slip surface: all off
        # lightmap res scale, photon fidelity, two-sided tint, override transparency,
        # additive tint, shader gel, ignore default res scale
        f"BM_LMRES {res:.10f} 1 0.0000000000 0.0000000000 0.0000000000 0 "
        "0.0000000000 0.0000000000 0.0000000000 0 0",
        f"BM_LIGHTING_BASIC {power:.10f} {r:.10f} {g:.10f} {b:.10f} {quality:.10f} "
        f"{int(per_area)} {focus:.10f}",
        f"BM_LIGHTING_ATTEN 1 {falloff * 100:.10f} {cutoff * 100:.10f}",
        "BM_LIGHTING_FRUS 0.0000000000 25.0000000000 45.0000000000",
    ]


def terrain_shader_lines(names, stock_dir, level_dir, group="shader_terrain"):
    """mbedit lines that copy shaders, unchanged, from a folder no collection
    prefix reaches into the level's own shaders folder, so their prefix-free
    names resolve. Run before tool structure."""
    lines = []
    for name in names:
        lines += [f"load\t{stock_dir}\\{name}\t{group}",
                  f"saveas\t{level_dir}\\shaders\\{name}\t{group}"]
    return lines


def atmosphere_lines(stock, new, edits, setting=0):
    """mbedit lines: a copy of a stock sky_atm_parameters tag with some of one
    atmosphere setting's fields changed ({field: value})."""
    lines = [f"load\t{stock}\tsky_atm_parameters"]
    for field, value in edits.items():
        lines.append(f"set\tatmosphere settings[{setting}]/{field}\t{value}")
    lines.append(f"saveas\t{new}\tsky_atm_parameters")
    return lines


def sky_lines(stock_dir, stock_name, new, empty_regions, sky_resources, new_sky_resources):
    """mbedit lines: a copy of a stock sky (render model, model, scenery) with
    some render model regions emptied, and a copy of the stock sky references
    resource pointing at it. stock_dir holds `sky.render_model` and
    `<stock_name>.model/.scenery`."""
    lines = [f"load\t{stock_dir}\\sky\trender_model"]
    for i in empty_regions:
        lines += [f"set\tregions[{i}]/permutations[0]/mesh index\t-1",
                  f"set\tregions[{i}]/permutations[0]/mesh count\t0"]
    lines += [f"saveas\t{new}\trender_model",
              f"load\t{stock_dir}\\{stock_name}\tmodel",
              f"set\trender model\t{new},render_model",
              f"saveas\t{new}\tmodel",
              f"load\t{stock_dir}\\{stock_name}\tscenery",
              f"set\tobject/model\t{new},model",
              f"saveas\t{new}\tscenery",
              f"load\t{sky_resources}\tscenario_sky_references_resource",
              f"set\tskies[0]/sky\t{new},scenery",
              f"saveas\t{new_sky_resources}\tscenario_sky_references_resource"]
    return lines


def cluster_data_lines(stock_resources, new_resources, bsp, per_cluster, clusters=1, centroid=(0, 0, 20)):
    """mbedit lines: a copy of the stock cluster data resource for the new BSP,
    giving each of its `clusters` the palette entries in per_cluster
    ({block: palette index, -1 none}: acoustics, atmospheric properties...).
    A sealed box level with no portals has one cluster."""
    lines = [f"load\t{stock_resources}\tscenario_cluster_data_resource",
             f"set\tcluster data[0]/bsp\t{bsp},scenario_structure_bsp"]
    for block, index in per_cluster.items():
        lines.append(f"clear\tcluster data[0]/{block}")
        for c in range(clusters):
            lines += [f"add\tcluster data[0]/{block}",
                      f"set\tcluster data[0]/{block}[{c}]/type\t{index}"]
    lines.append("clear\tcluster data[0]/cluster centroids")
    for c in range(clusters):
        lines += ["add\tcluster data[0]/cluster centroids",
                  f"set\tcluster data[0]/cluster centroids[{c}]/centroid\t{','.join(str(v) for v in centroid)}"]
    lines.append(f"saveas\t{new_resources}\tscenario_cluster_data_resource")
    return lines
