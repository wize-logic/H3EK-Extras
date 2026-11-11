"""A heightfield terrain: heights H[i, j] at (xs[i], xs[j]) on a square grid,
read exactly as ass.ground_tiles writes them (two triangles per cell), with
the API scenario.Plan and the layout code use."""

import math

import numpy as np


class Heightfield:
    def __init__(self, xs, H):
        self.xs, self.H = np.asarray(xs), np.asarray(H)
        self.step = float(self.xs[1] - self.xs[0])

    @classmethod
    def load(cls, path):
        """From an .npz holding xs and H."""
        data = np.load(path)
        return cls(data["xs"], data["H"])

    def save(self, path):
        np.savez_compressed(path, xs=self.xs, H=self.H)

    def _at(self, x, y):
        fx = (x - self.xs[0]) / self.step
        fy = (y - self.xs[0]) / self.step
        i, j = int(math.floor(fx)), int(math.floor(fy))
        if not (0 <= i < len(self.xs) - 1 and 0 <= j < len(self.xs) - 1):
            return None
        u, v = fx - i, fy - j
        H = self.H
        # the two triangles of each cell, as written to the mesh
        if v <= u:   # triangle (i,j) (i+1,j) (i+1,j+1)
            return H[i, j] + u * (H[i + 1, j] - H[i, j]) + v * (H[i + 1, j + 1] - H[i + 1, j])
        return H[i, j] + v * (H[i, j + 1] - H[i, j]) + u * (H[i + 1, j + 1] - H[i, j + 1])

    def height(self, x, y, r=0.0):
        """Highest ground within r of (x, y)."""
        pts = [(x, y)] if r <= 0 else [(x + a, y + b) for a in (-r, 0, r) for b in (-r, 0, r)]
        hs = [h for h in (self._at(*p) for p in pts) if h is not None]
        return max(hs) if hs else None

    def ground(self, x, y):
        return self._at(x, y)

    def slope(self, x, y, d=2.0):
        """Rise over run across 2d around (x, y)."""
        hx = (self._at(x + d, y) - self._at(x - d, y)) / (2 * d)
        hy = (self._at(x, y + d) - self._at(x, y - d)) / (2 * d)
        return math.hypot(hx, hy)
