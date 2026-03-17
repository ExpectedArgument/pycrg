from __future__ import annotations

import argparse
from dataclasses import dataclass
from math import fabs
from pathlib import Path

from pycrg import (
    BORDER_MODE_EX_KEEP,
    BORDER_MODE_EX_ZERO,
    BORDER_MODE_NONE,
    BORDER_MODE_REFLECT,
    BORDER_MODE_REPEAT,
    CP_OPTION_BORDER_MODE_U,
    CP_OPTION_BORDER_MODE_V,
    CP_OPTION_BORDER_OFFSET_U,
    CP_OPTION_BORDER_OFFSET_V,
    CP_OPTION_CURV_MODE,
    CP_OPTION_REF_LINE_CONTINUE,
    CP_OPTION_SMOOTH_U_BEGIN,
    CP_OPTION_SMOOTH_U_END,
    CURV_REF_LINE,
    DataSet,
    GRID_NAN_KEEP_LAST,
    MOD_GRID_NAN_MODE,
    MOD_REF_LINE_OFFSET_PHI,
    MOD_REF_LINE_OFFSET_X,
    MOD_REF_LINE_OFFSET_Y,
    MOD_REF_LINE_OFFSET_Z,
    MOD_REF_LINE_ROT_CENTER_X,
    MOD_REF_LINE_ROT_CENTER_Y,
    MOD_REF_POINT_U,
    MOD_REF_POINT_V,
    MOD_REF_POINT_X,
    MOD_REF_POINT_Y,
    MOD_REF_POINT_Z,
    MOD_SCALE_BANK,
    MOD_SCALE_CURVATURE,
    MOD_SCALE_LENGTH,
    MOD_SCALE_SLOPE,
    MOD_SCALE_WIDTH,
    MOD_SCALE_Z,
    MSG_LEVEL_FATAL,
    REF_LINE_CLOSE_TRACK,
    REF_LINE_EXTRAPOLATE,
    get_release_info,
    set_message_callback,
    set_message_level,
)


def default_input_file() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "tests" / "data" / "sample.crg",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


@dataclass
class MessageCounter:
    count: int = 0

    def __call__(self, level: int, message: str) -> int:
        self.count += 1
        clean = message.rstrip("\n")
        print(f"myMsgHandler: got msg no. {self.count}, level = {level}, text = <{clean}>")
        return 0


def apply_test_configuration(dataset: DataSet, cp, test_no: int) -> bool:
    if test_no >= 0:
        cp.set_default_options()

    if test_no == -1:
        print("test purpose: using options / modifiers from file")
    elif test_no == 0:
        print("test purpose: default settings")
    elif test_no == 1:
        print("test purpose: curvature on reference line")
        cp.option_set_int(CP_OPTION_CURV_MODE, CURV_REF_LINE)
    elif test_no == 2:
        print("test purpose: refuse query exceeding u dimensions of data")
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_NONE)
    elif test_no == 3:
        print("test purpose: set elevation to zero when exceeding u and v dimensions of data")
        cp.option_set_double(CP_OPTION_BORDER_OFFSET_U, -1.0)
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_EX_ZERO)
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_EX_ZERO)
    elif test_no == 4:
        print("test purpose: keep last value when exceeding u dimensions of data")
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_EX_KEEP)
    elif test_no == 5:
        print("test purpose: repeat data in u direction")
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_REPEAT)
    elif test_no == 6:
        print("test purpose: reflect data in u direction")
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_REFLECT)
    elif test_no == 7:
        print("test purpose: repeat data in u direction with offset")
        cp.option_set_double(CP_OPTION_BORDER_OFFSET_U, 1.0)
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_REPEAT)
    elif test_no == 8:
        print("test purpose: refuse query exceeding v dimensions of data")
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_NONE)
    elif test_no == 9:
        print("test purpose: set elevation to zero when exceeding v dimensions of data")
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_EX_ZERO)
    elif test_no == 10:
        print("test purpose: keep last value when exceeding v dimensions of data")
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_EX_KEEP)
    elif test_no == 11:
        print("test purpose: repeat data in v direction")
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_REPEAT)
    elif test_no == 12:
        print("test purpose: reflect data in v direction")
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_REFLECT)
    elif test_no == 13:
        print("test purpose: repeat data in v direction with offset")
        cp.option_set_double(CP_OPTION_BORDER_OFFSET_V, 1.0)
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_REPEAT)
    elif test_no == 14:
        print("test purpose: 10.0m smoothing zone at the begin")
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_EX_ZERO)
        cp.option_set_double(CP_OPTION_SMOOTH_U_BEGIN, 10.0)
    elif test_no == 15:
        print("test purpose: 10.0m smoothing zone at the end")
        cp.option_set_double(CP_OPTION_SMOOTH_U_END, 10.0)
    elif test_no == 16:
        print("test purpose: extrapolating reference line")
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_EX_KEEP)
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_EX_KEEP)
        cp.option_set_int(CP_OPTION_REF_LINE_CONTINUE, REF_LINE_EXTRAPOLATE)
    elif test_no == 17:
        print("test purpose: continuing (closing) reference line")
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_EX_KEEP)
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_NONE)
        cp.option_set_int(CP_OPTION_REF_LINE_CONTINUE, REF_LINE_CLOSE_TRACK)
    elif test_no == 18:
        print("test purpose: z scaling")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_SCALE_Z, 2.0)
    elif test_no == 19:
        print("test purpose: slope scaling")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_SCALE_SLOPE, 10.0)
    elif test_no == 20:
        print("test purpose: bank scaling")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_SCALE_BANK, 10.0)
    elif test_no == 21:
        print("test purpose: length scaling")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_SCALE_LENGTH, 2.0)
    elif test_no == 22:
        print("test purpose: width scaling")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_SCALE_WIDTH, 2.0)
    elif test_no == 23:
        print("test purpose: curvature scaling")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_SCALE_CURVATURE, 0.5)
    elif test_no == 24:
        print("test purpose: curvature scaling")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_SCALE_CURVATURE, 0.0)
    elif test_no == 25:
        print("test purpose: repositioning by u and v")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_REF_POINT_U, 5.0)
        dataset.modifier_set_double(MOD_REF_POINT_V, 1.5)
        dataset.modifier_set_double(MOD_REF_POINT_X, 100.0)
        dataset.modifier_set_double(MOD_REF_POINT_Y, 200.0)
        dataset.modifier_set_double(MOD_REF_POINT_Z, 10.0)
    elif test_no == 26:
        print("test purpose: repositioning by dx/dy/dz")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_REF_LINE_OFFSET_X, 100.0)
        dataset.modifier_set_double(MOD_REF_LINE_OFFSET_Y, 200.0)
        dataset.modifier_set_double(MOD_REF_LINE_OFFSET_Z, 10.0)
    elif test_no == 27:
        print("test purpose: repositioning by dphi around rx,ry and translated by dx/dy/dz")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_REF_LINE_ROT_CENTER_X, 0.0)
        dataset.modifier_set_double(MOD_REF_LINE_ROT_CENTER_Y, 0.0)
        dataset.modifier_set_double(MOD_REF_LINE_OFFSET_PHI, 1.57)
        dataset.modifier_set_double(MOD_REF_LINE_OFFSET_X, 100.0)
        dataset.modifier_set_double(MOD_REF_LINE_OFFSET_Y, 100.0)
        dataset.modifier_set_double(MOD_REF_LINE_OFFSET_Z, 100.0)
    elif test_no == 28:
        print("test purpose: repositioning by dphi")
        dataset.modifier_remove_all()
        dataset.modifier_set_int(MOD_GRID_NAN_MODE, GRID_NAN_KEEP_LAST)
        dataset.modifier_set_double(MOD_REF_LINE_OFFSET_PHI, -0.6981317)
        cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_EX_ZERO)
        cp.option_set_int(CP_OPTION_BORDER_MODE_V, BORDER_MODE_EX_ZERO)
    else:
        return False

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Python port of OpenCRG C demo: EvalOptions")
    parser.add_argument("filename", nargs="?", default=str(default_input_file()), help="Input .crg file")
    parser.add_argument("-t", "--test", type=int, default=None, help="Run only a single test number")
    parser.add_argument("-p", "--plot", action="store_true", help="Write output data to crgPlotData.txt")
    args = parser.parse_args()

    handler = MessageCounter()
    set_message_callback(handler)

    print(f"Library version info: <{get_release_info()}>")

    plot_file = None
    if args.plot:
        plot_file = open("crgPlotData.txt", "w", encoding="utf-8")
        set_message_level(MSG_LEVEL_FATAL)

    n_steps_u = 22
    n_steps_v = 6
    n_excess_steps_u = 50
    n_excess_steps_v = 10

    dataset = DataSet.open(args.filename)
    if not dataset.check():
        raise RuntimeError("could not validate crg data")

    cp = dataset.create_contact_point()

    single_test = args.test is not None
    test_no = args.test if args.test is not None else 0
    while True:
        print("--------------------------------------------------------------")
        print(f"Starting test no. {test_no}")

        if not apply_test_configuration(dataset, cp, test_no):
            print("all tests finished")
            break

        dataset.modifiers_apply()

        u_min, u_max = dataset.u_range()
        v_min, v_max = dataset.v_range()
        du = (u_max - u_min) / n_steps_u
        dv = (v_max - v_min) / n_steps_v

        u_max += n_excess_steps_u * du
        u_min -= n_excess_steps_u * du
        v_max += n_excess_steps_v * dv
        v_min -= n_excess_steps_v * dv

        cp.options_print()

        for i in range(0, n_steps_u + 2 * n_excess_steps_u + 1):
            u = u_min + du * i
            for j in range(0, n_steps_v + 2 * n_excess_steps_v + 1):
                v = v_min + dv * j
                z_uv = cp.try_uv_to_z(u, v)
                if z_uv is None:
                    print(f"warning: error converting u/v = {u:+10.4f} / {v:+10.4f} to z")
                    continue

                xy = cp.try_uv_to_xy(u, v)
                if xy is None:
                    print(f"warning: error converting u/v = {u:+10.4f} / {v:+10.4f} to x/y")
                    continue
                x, y = xy

                z_xy = cp.try_xy_to_z(x, y)
                if z_xy is None:
                    print(f"warning: error converting x/y = {x:+10.4f} / {y:+10.4f} to z")
                    continue

                if plot_file is not None:
                    plot_file.write(f" {x:+10.4f}  {y:+10.4f}  {z_xy:+10.4f}\n")

                if fabs(z_xy - z_uv) > 1.0e-4:
                    uv = cp.try_xy_to_uv(x, y)
                    if uv is None:
                        print(f"warning: error converting x/y = {x:+10.4f} / {y:+10.4f} to u/v")
                        continue
                    u_comp, v_comp = uv
                    print(
                        "inconsistent chain: "
                        f"u/v {u:.3f}/{v:.3f} -> x/y {x:+10.4f}/{y:+10.4f} -> "
                        f"u/v {u_comp:+.16f}/{v_comp:+.16f} -> z {z_xy:+10.4f}"
                    )
                    print(f"warning: inconsistent z values: {z_uv:+10.4f} vs {z_xy:+10.4f}")

        print(f"Finished test no. {test_no}\n")

        if single_test:
            break
        test_no += 1

    cp.close()
    dataset.close()

    if plot_file is not None:
        plot_file.close()

    set_message_callback(None)
    print("normal termination")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
