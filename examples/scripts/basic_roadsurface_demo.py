from __future__ import annotations

from pathlib import Path

from pycrg import RoadSurface

if __name__ == "__main__":
    sample = Path(__file__).resolve().parents[2] / "tests" / "data" / "crg-txt" / "handmade_curved.crg"

    # load the file, apply its modifiers and create a contact point
    with RoadSurface.open(sample, check=True) as road:
        print("u range:", road.u_range())
        print("v range:", road.v_range())
        print("z(10, 0.5):", road.uv_to_z(10.0, 0.5))
        print("x/y(10, 0.5):", road.uv_to_xy(10.0, 0.5))
        print("heading/curvature(10, 0):", road.uv_to_pk(10.0, 0.0))
