from __future__ import annotations

import argparse
from math import fabs
from pathlib import Path

from pycrg import DataSet, MSG_LEVEL_NOTICE, set_message_level


def default_input_file() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "tests" / "data" / "sample.crg",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Python port of OpenCRG C demo: EvalXYnUV")
    parser.add_argument("filename", nargs="?", default=str(default_input_file()), help="Input .crg file")
    args = parser.parse_args()

    n_steps_u = 20
    n_steps_v = 20
    n_border_u = 10
    n_border_v = 10

    set_message_level(MSG_LEVEL_NOTICE)

    dataset = DataSet.open(args.filename)
    if not dataset.check():
        raise RuntimeError("could not validate crg data")

    dataset.modifiers_print()
    dataset.modifiers_apply()

    cp = dataset.create_contact_point()

    u_min, u_max = dataset.u_range()
    v_min, v_max = dataset.v_range()
    du = (u_max - u_min) / n_steps_u
    dv = (v_max - v_min) / n_steps_v

    for i in range(-n_border_u, n_steps_u + n_border_u + 1):
        u = u_min + du * i
        for j in range(-n_border_v, n_steps_v + n_border_v + 1):
            v = v_min + dv * j
            xy = cp.try_uv_to_xy(u, v)
            if xy is None:
                print(f"warning: error converting u/v = {u:+10.4f} / {v:+10.4f} to x/y")
                continue
            x, y = xy

            uv_back = cp.try_xy_to_uv(x, y)
            if uv_back is None:
                print(f"warning: error converting x/y = {x:+10.4f} / {y:+10.4f} to u/v")
                continue
            u_back, v_back = uv_back
            delta_u = u - u_back
            delta_v = v - v_back
            print(
                f"u/v = {u:+10.4f} / {v:+10.4f} -> x/y = {x:+10.4f} / {y:+10.4f} -> "
                f"u/v = {u_back:+10.4f} / {v_back:+10.4f}"
            )
            if fabs(delta_u) > 1.0e-5 or fabs(delta_v) > 1.0e-5:
                print(f"computation error when converting back: du/dv = {delta_u:.8f} / {delta_v:.8f}")

    cp.close()
    dataset.close()
    print("normal termination")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
