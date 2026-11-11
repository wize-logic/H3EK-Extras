# Example map

The smallest complete map built with [h3kit](../../h3kit/README.md): rolling ground 300 units across with a hill in the middle, a bunker per team (lit by a light strip), and a two-team CTF and King of the Hill layout with spawns, a few vehicles and weapons. It starts from Avalanche's scenario (its sky, game setup and Forge palettes).

Copy this folder to start a new map; [the toolkit's README](../../h3kit/README.md#starting-a-new-map) says what to change.

| File | What it is |
| --- | --- |
| `project.py` | Names, ids and the package metadata. Change all of them in a copy. |
| `look.py` | Shaders per surface key, texture sizes, the light material and its fixtures, and the cluster data that brings Avalanche's atmosphere and sounds to the new level. |
| `level.py` | The ground (a `Heightfield`, saved to `ground.npz`) and the bunkers (`h3kit.mesh`), written as the level `.ASS`. |
| `build.py` | The layout (`ExamplePlan`) and the map's `build.Map`. |

```bash
python3 maps/example/level.py /tmp/example.ASS                 # the level, anywhere (no kit changes)
python3 maps/example/build.py --plan-only --script-out /tmp/x  # the layout, budgets and the mbedit script
python3 -u maps/example/build.py --light draft                 # compile, bake and build maps\h3kit_example.map
```

The level and the scenario script are generated and checked without the kit (no coplanar overlaps, budgets fine); the example has not been through a full build yet, so treat its first `--light draft` build as the test.
