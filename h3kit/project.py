"""What makes one map different from another, in one place.

A map folder (maps/<map>/project.py) builds a Project and calls use(): from
then on every h3kit module that needs a map's names, tag folders, budgets or
ids reads them from active(). Nothing in h3kit reads a project at import
time, so a map can import h3kit modules before or after use().

    PROJECT = use(Project(name="my_map", level_dir="levels\\\\dlc\\\\my_map",
                          base=BaseMap("levels\\\\dlc\\\\sidewinder\\\\sidewinder", ...),
                          map_id=9000, root=Path(__file__).parent))
"""

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import env


@dataclass
class BaseMap:
    """The stock multiplayer map a new map starts from. Its scenario is
    copied: the sky, the game setup and the Forge palettes stay, its level and
    objects are replaced."""
    scenario: str                    # e.g. levels\dlc\sidewinder\sidewinder
    resources: str                   # its split resource tags' path stem: levels\dlc\sidewinder\resources\sidewinder
    map_file: str = ""               # its built map in MCC's halo3\maps (sidewinder.map)
    # trigger volumes to rename out of service (a "kill" or "safe_zone" name is what makes them work)
    retired_volumes: dict = field(default_factory=dict)
    # objects its scenario still creates once its placements are cleared: (tag, type, count),
    # for the object-memory budget (object_memory.py)
    stock_objects: list = field(default_factory=list)

    @property
    def name(self):
        return self.scenario.split("\\")[-1]

    @property
    def xml_name(self):
        """export_xml cache name of its scenario."""
        return f"{self.name}_scenario.xml"


@dataclass
class Mod:
    """The MCC mod package's metadata (ModInfo.json and the map's JSON). Keep
    the GUIDs and the Workshop id once published, so an upload updates the same
    item instead of creating a new one."""
    title: str                       # the package's folder name (Mods\<title>)
    shown_title: str                 # the Workshop and map list title
    description: str
    mod_guid: str
    map_guid: str
    workshop_id: int = 0
    version: tuple = (1, 0, 0)
    app_versions: tuple = ((1, 3385, 0), (1, 3528, 0))   # MCC builds Excession sets (min, max)
    max_teams: int = 2
    flags: tuple = ("DisableSavedFilms",)
    upload_dir: Path = None          # the folder Excession uploads from (Documents\<shown title>)
    # the shipped map's file name (maps\<file_name>.map, the JSON's ScenarioFile), when it is
    # not the scenario's name. Project Reclaimer's loading screen shows a mod map's name as
    # this file name in capitals ("_" as spaces): it reads the proper name only from a
    # .mapinfo in MCC's own halo3\maps\info, which a mod cannot add to.
    file_name: str = None


@dataclass
class Project:
    name: str                        # scenario file name, map file name: <name>.map
    level_dir: str                   # tags folder of the new scenario: levels\dlc\<name>
    base: BaseMap
    map_id: int                      # the scenario's map id; also seeds the layout and the .ASS instance ids
    root: Path                       # the map's folder in this repository
    bsp_dir: str = None              # tags folder of the new level (default: level_dir)
    bsp_name: str = None             # the level's .ASS / structure bsp name (default: name)
    object_dir: str = None           # tags folder for the map's own objects (default: objects\<level_dir>)
    mod: Mod = None
    # stock vehicles and weapons the base map's Forge palette lacks: added so they respawn
    forge_vehicles: tuple = ()
    forge_weapons: tuple = ()
    donors: list = field(default_factory=list)   # donor.Donor: tags ported from other built maps
    machine_budget: int = 400        # static props as device machines (machines.py; engine cap 600)
    light_job: str = "111"           # the light bake's job folder, H3EK\faux\<job> (numeric)
    ass_header: tuple = ("h3kit", "H3KIT")   # the .ASS header's user and machine names
    light_stamp_name: str = None     # H3EK\work file recording the last bake (default <name>_light_stamp.json)

    def __post_init__(self):
        self.root = Path(self.root)
        self.bsp_dir = self.bsp_dir or self.level_dir
        self.bsp_name = self.bsp_name or self.name
        self.object_dir = self.object_dir or "objects\\" + self.level_dir

    # -- tag paths (relative to H3EK\tags, no extension) ---------------------------
    @property
    def scenario(self):
        return f"{self.level_dir}\\{self.name}"

    @property
    def resources(self):
        """The new scenario's split resource tags' path stem."""
        return f"{self.level_dir}\\resources\\{self.name}"

    @property
    def bsp(self):
        return f"{self.bsp_dir}\\{self.bsp_name}"

    def tag_dir(self, sub):
        """A folder for tags the build makes: objects\\...\\<sub>."""
        return f"{self.object_dir}\\{sub}"

    def level_tag_dir(self, sub):
        """A folder for level tags the build makes: levels\\...\\<sub>."""
        return f"{self.level_dir}\\{sub}"

    # -- files --------------------------------------------------------------------
    @property
    def ass_path(self):
        """The level's .ASS (the kit's data folder)."""
        return env.EK / "data" / Path(*self.bsp_dir.split("\\")) / "structure" / f"{self.bsp_name}.ASS"

    @property
    def bsp_tag(self):
        return env.EK / "tags" / Path(*self.bsp_dir.split("\\")) / f"{self.bsp_name}.scenario_structure_bsp"

    @property
    def built_map(self):
        """Where build-cache-file writes the map."""
        return env.EK / "maps" / f"{self.name}.map"

    @property
    def package_dir(self):
        """The mod package (the folder Excession uploads)."""
        return self.root / "package"

    @property
    def file_name(self):
        """The shipped map's file name: the Mod's file_name, else the scenario's name."""
        return (self.mod and self.mod.file_name) or self.name

    @property
    def package_map(self):
        return self.package_dir / "maps" / f"{self.file_name}.map"

    @property
    def light_stamp(self):
        """What the last full light bake was made from (build.py --reuse-light)."""
        return env.WORK / (self.light_stamp_name or f"{self.name}_light_stamp.json")

    @property
    def collision_dump(self):
        """The level's collision (mbedit bspdump), for the layout's standing-room checks."""
        return env.WORK / f"{self.name}_collision.txt"


_ACTIVE = None


def use(project):
    """Make `project` the one h3kit works for, and register its donors' tags."""
    global _ACTIVE
    _ACTIVE = project
    for d in project.donors:
        d.register()
    return project


def active():
    if _ACTIVE is None:
        raise RuntimeError("no h3kit project: import the map's project.py first (it calls h3kit.project.use)")
    return _ACTIVE


def load(map_dir):
    """Import a map folder's project.py (which calls use()) and return its project."""
    d = str(Path(map_dir).resolve())
    if d not in sys.path:
        sys.path.insert(0, d)
    importlib.import_module("project")
    return active()
