"""The example map's settings: the smallest complete h3kit map, to copy when
starting a new one (see README.md). Change every name and id below: a new
`name` and `level_dir`, a map_id no other map of yours uses, and new GUIDs
(python3 -c "import uuid; print(uuid.uuid4())").

Every module of a map imports this first: it puts the repository on the
import path and makes this the active h3kit project.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parents[1]) not in sys.path:
    sys.path.insert(0, str(HERE.parents[1]))   # the repository: h3kit

from h3kit.bases import SIDEWINDER, SIDEWINDER_FORGE_VEHICLES, SIDEWINDER_FORGE_WEAPONS  # noqa: E402
from h3kit.project import Mod, Project, use  # noqa: E402

PROJECT = use(Project(
    name="h3kit_example",                    # the scenario and maps\h3kit_example.map
    level_dir="levels\\dlc\\h3kit_example",  # where its tags go under H3EK\tags
    base=SIDEWINDER,                         # Avalanche's sky, game setup and Forge palettes
    map_id=8471,
    root=HERE,
    forge_vehicles=SIDEWINDER_FORGE_VEHICLES,
    forge_weapons=SIDEWINDER_FORGE_WEAPONS,
    mod=Mod(title="H3kit Example", shown_title="H3kit Example",
            description="A small two-base Capture the Flag map built with h3kit.",
            mod_guid="39c5dd81-9285-453e-88f1-fa8de44a3830",
            map_guid="0eccaff0-0bd8-44f1-beca-0bf5b7a402a9"),
))
