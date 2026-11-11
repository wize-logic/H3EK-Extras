# H3EK-Extras

Tools to help you create with H3EK: build Halo 3 (MCC) multiplayer maps with the Halo 3 Editing Kit from code.

| Folder | What it is |
| --- | --- |
| [`h3kit/`](h3kit/README.md) | A Python toolkit that drives the kit: paths and the kit's tools, placements and the scenario edit, meshes, the level's `.ASS` and its lights, the light bake and its reuse, machines, object memory, decorators, a prop catalog, imported props, vehicles from other built maps, the Workshop package, map packs. |
| [`tools/`](tools/README.md) | Native helpers: `mbedit` (a scripted tag editor on ManagedBlam) and `hgport` (moves compiled tags between built maps). |
| [`maps/example/`](maps/example/README.md) | The smallest complete map: copy it to start a new one. |
| [`docs/`](docs/tools.md) | Reference: the tools and logs, the Editing Kit, the cache format, engine limits. |

## Quick start

You need Windows with WSL, MCC with Halo 3, the Halo 3 Editing Kit with its tags extracted, Python for Windows, and Python 3 with `numpy` and `Pillow` in WSL. Then, in WSL, from this folder:

```bash
tools/mbedit/build.sh                                  # the tag editor, into H3EK\work (once)
python3 -m h3kit maps/example                          # check the setup
python3 maps/example/build.py --plan-only              # the layout and budgets, no kit changes
python3 -u maps/example/build.py --light draft         # compile, bake and build the map
```

Starting a map of your own: [h3kit/README.md](h3kit/README.md#starting-a-new-map).

## Documentation

- [h3kit/README.md](h3kit/README.md): setting up, how a map is put together, the build, the modules.
- [docs/tools.md](docs/tools.md): every tool and path, and the logs worth reading.
- [docs/h3ek.md](docs/h3ek.md): the Halo 3 Editing Kit: tool, ManagedBlam, mbedit's script language, the scenario tag.
- [docs/halo3-formats.md](docs/halo3-formats.md): the cache file format and the scenario's layout in it.
- [docs/runtime-limits.md](docs/runtime-limits.md): engine limits (object slots, memory, respawns), with their sources.

## Licence

`tools/hgport` includes Assembly's Blamite library and is under the GNU GPL v3: see [tools/README.md](tools/README.md#licence).
