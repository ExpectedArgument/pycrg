from __future__ import annotations

from pathlib import Path

from pycrg import RoadSurface


if __name__ == "__main__":
    sample = Path(__file__).resolve().parents[2] / "tests" / "data" / "sample.crg"

    road = RoadSurface.open(str(sample))
    print("u range:", road.u_range())
    print("v range:", road.v_range())
    print("z(0,0):", road.uv_to_z(0.0, 0.0))
    print("pk(0,0):", road.uv_to_pk(0.0, 0.0))
    road.close()
