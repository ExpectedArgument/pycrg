"""Write a synthetic road with pycrg.write and evaluate it with numpy."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

import pycrg

if __name__ == "__main__":
    # 100 m of road, 4 m wide, a cross section every 5 cm, a long section every 10 cm
    du = 0.05
    u = np.arange(0.0, 100.0 + du / 2, du)
    v = np.linspace(-2.0, 2.0, 41)
    rng = np.random.default_rng(1)
    z = 0.002 * rng.standard_normal((u.size, v.size)) + 0.01 * np.sin(u / 3.0)[:, None]

    # a gentle left curve: the heading of each segment between cross sections
    headings = 0.3 + 0.002 * np.arange(u.size - 1)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "synthetic.crg"
        pycrg.write(
            path,
            z,
            du,
            v,
            headings,
            x0=500.0,
            y0=200.0,
            banking=0.02,
            comment=["synthetic road written by pycrg"],
            mods={},  # an empty modifier section keeps the road where it is
        )
        print(path.stat().st_size, "bytes written")

        header = pycrg.read_header(path)
        start = header.road["reference_line_start_x"], header.road["reference_line_start_y"]
        print("format:", header.data_format, "start:", start)

        with pycrg.RoadSurface.open(path, check=True) as road:
            # evaluate a whole grid at once
            uu, vv = np.meshgrid(np.linspace(0.0, 100.0, 201), np.linspace(-2.0, 2.0, 9), indexing="ij")
            elevation = road.uv_to_z_many(uu, vv)
            print("elevation grid:", elevation.shape, "range:", np.nanmin(elevation), np.nanmax(elevation))

            # positions of the left road edge in x/y
            x, y = road.uv_to_xy_many(u, 2.0)
            print("left edge from", (float(x[0]), float(y[0])), "to", (float(x[-1]), float(y[-1])))

            # the stored data, as used for evaluation
            grid = road.grid()
            print(
                "grid:",
                grid.z.shape,
                "max |elevation - uv_to_z|:",
                np.max(np.abs(grid.elevation - road.uv_to_z_many(grid.u[:, None], grid.v[None, :]))),
            )
