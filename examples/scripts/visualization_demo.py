"""Show OpenCRG data with pycrg.plot, like crg_show and its companions of the OpenCRG MATLAB tools.

Needs matplotlib (pip install "pycrg[plot]"). Displays the figures, or writes them as PNG files to
the directory given with --output.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

import pycrg
import pycrg.plot


def default_input_file() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "data" / "crg-txt" / "handmade_curved.crg"


def main() -> int:
    parser = argparse.ArgumentParser(description="Show a CRG file and synthetic roads with pycrg.plot")
    parser.add_argument("filename", nargs="?", default=str(default_input_file()), help="Input .crg file")
    parser.add_argument("--output", type=Path, help="write the figures as PNG files to this directory")
    args = parser.parse_args()
    if args.output is not None:
        matplotlib.use("Agg")  # draw without a display

    figures = []
    with pycrg.DataSet.open(args.filename, check=True) as dataset:
        # all figures of crg_show
        figures += dataset.show()

        # single plots in a figure of your own
        fig, (left, right) = plt.subplots(1, 2, figsize=(11.69, 4.5), layout="constrained")
        pycrg.plot.plot_elgrid_cross_sect(dataset, ax=left)
        pycrg.plot.plot_refline_curvature(dataset, ax=right)
        figures.append(fig)

        # the road surface on a grid of your own, 1 m wider than the data on both sides
        u = np.linspace(*dataset.u_range(), 200)
        v_min, v_max = dataset.v_range()
        v = np.linspace(v_min - 1.0, v_max + 1.0, 50)
        figures.append(pycrg.plot.show_road_uv2surface(dataset, u, v))

    with tempfile.TemporaryDirectory() as tmp:
        # a synthetic road, 30 m long and 4 m wide, with a bump and a pothole
        v = np.linspace(-2.0, 2.0, 41)
        z = 0.003 * np.sin(np.arange(301)[:, None] / 9.0) * np.cos(v[None, :])
        z[100, 12] = 0.2
        z[220, 30] = -0.15
        road = Path(tmp) / "road.crg"
        pycrg.write(road, z, 0.1, v, 0.002 * np.arange(300), mods={})

        # the same road with a resurfaced patch
        resurfaced = z.copy()
        resurfaced[150:200, 5:25] += 0.01
        other = Path(tmp) / "resurfaced.crg"
        pycrg.write(other, resurfaced, 0.1, v, 0.002 * np.arange(300), mods={})

        with pycrg.DataSet.open(road) as a, pycrg.DataSet.open(other) as b:
            peaks = pycrg.find_peaks(a)  # crg_peakfinder
            for u_peak, v_peak, z_peak in zip(peaks.u, peaks.v, peaks.z, strict=True):
                print(f"peak at u = {u_peak:g} m, v = {v_peak:g} m: z = {z_peak:g} m")
            figures.append(pycrg.plot.show_peaks(a, peaks))

            result = pycrg.compare(a, b)  # crg_isequal
            print("identical" if result.identical else "different", f"(max |dz| = {result.max_difference:g} m)")
            figures.append(pycrg.plot.show_isequal(result))

    if args.output is None:
        plt.show()
    else:
        args.output.mkdir(parents=True, exist_ok=True)
        for number, fig in enumerate(figures, 1):
            path = args.output / f"figure-{number:02d}.png"
            fig.savefig(path)
            print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
