"""Build the example map: level.py's ground and bunkers, a two-team CTF and
KOTH layout, compiled with the Halo 3 Editing Kit.

    python3 maps/example/build.py --plan-only --script-out /tmp/x.txt   # layout + script, no kit changes
    python3 -u maps/example/build.py --light draft                      # a full build with a quick bake
    python3 -u maps/example/build.py --reuse-light                      # objects only, after a full build

The layout is written for red (+x) and turned 180 degrees about the origin
for blue, like the level.
"""

import math

import project  # noqa: F401  (this map's h3kit settings)
from h3kit import build
from h3kit.scenario import Placement, Plan
from h3kit.stock import BLUE, MUST, NEUTRAL, RED

import level
import look


def twin(x, y, team):
    return (x, y) if team == RED else (-x, -y)


def twin_yaw(yaw, team):
    return yaw % 360.0 if team == RED else (yaw + 180.0) % 360.0


class ExamplePlan(Plan):
    def build(self):
        floor = 0.2 + 0.02          # the bunker floor's top (level.bunker), plus a hair
        for team in (RED, BLUE):
            bx = level.BASE_X
            face = 180.0            # red faces the centre (-x)
            # the flag in the bunker, scored at its return area
            fx, fy = twin(bx, 0.0, team)
            self.items.append(Placement("flag", (fx, fy, floor), team=team, priority=MUST))
            self.items.append(Placement("flag_return", (fx, fy, floor), team=team,
                                        boundary=("cylinder", 2.5, 0.0, 2.0, 1.0), priority=MUST))
            # spawns: initial ones in the bunker, respawns on the pad in front of it
            for k in range(4):
                x, y = twin(bx - 2.0, -3.0 + 2.0 * k, team)
                self.items.append(Placement("initial", (x, y, floor), twin_yaw(face, team), team=team, flags=0))
                self.items.append(Placement("koth_initial", (x, y, floor), twin_yaw(face, team), team=team, flags=0))
            for k in range(8):
                a = math.radians(140.0 + 10.0 * k)
                x, y = twin(bx + 12.0 * math.cos(a), 12.0 * math.sin(a), team)
                self.spawn(x, y, team, twin_yaw(face, team))
            zx, zy = twin(bx, 0.0, team)
            self.items.append(Placement("respawn_zone", (zx, zy, self.z(zx, zy)), team=team,
                                        boundary=("cylinder", 25.0, 0.0, 10.0, 5.0), flags=0))
            # vehicles beside the bunker, weapons on its floor
            for name, a, b in (("warthog", -6.0, 14.0), ("warthog", -6.0, -14.0), ("mongoose", 2.0, 14.0),
                               ("ghost", 2.0, -14.0)):
                x, y = twin(bx + a, b, team)
                self.vehicle(name, x, y, yaw=twin_yaw(face, team), team=team)
            for k, name in enumerate(("br", "br", "sniper", "rocket")):
                x, y = twin(bx - 4.0 + 2.0 * k, 4.0, team)
                self.weapon(name, x, y, z=floor + 0.1, team=team)
        # King of the Hill: the centre hill's top
        self.items.append(Placement("hill", (0.0, 0.0, self.z(0.0, 0.0) + 0.05), team=NEUTRAL,
                                    boundary=("cylinder", 6.0, 0.0, 5.0, 1.0), flags=0, spawn_order=1,
                                    priority=MUST))
        self.weapon("laser", 0.0, 3.0)
        return self


class Example(build.Map):
    def write_level(self, ass_path):
        level.write(ass_path)

    def terrain(self):
        return level.terrain()

    def plan(self, terrain, collision):
        return ExamplePlan(terrain).build()

    def tag_script(self, plan):
        return super().tag_script(plan) + look.tag_script()

    def scenario_lines(self):
        return look.scenario_lines()


MAP = Example()

if __name__ == "__main__":
    build.main(MAP, description=__doc__.splitlines()[0])
