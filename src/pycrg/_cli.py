"""The ``pycrg-show`` command: show an OpenCRG file like ``crg_show`` of the OpenCRG tools."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ._version import __version__

#: --figure names and the pycrg.plot functions creating them
_FIGURES = {
    "refline-map": "show_refline_map",
    "refline-elevation": "show_refline_elevation",
    "elgrid-cuts": "show_elgrid_cuts_and_limits",
    "elgrid-surface": "show_elgrid_surface",
    "road-surface": "show_road_surface",
    "info": "show_info",
}
#: figures of a whole data set, which take no index ranges
_WHOLE = {"info"}
#: the figures with long sections, which take an iv range
_WITH_IV = {"elgrid-cuts", "elgrid-surface", "road-surface"}

_NON_INTERACTIVE_BACKENDS = {"agg", "cairo", "pdf", "pgf", "ps", "svg", "template"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pycrg-show",
        description="Show an OpenCRG file in figures like crg_show of the OpenCRG tools, "
        "or write the figures to files.",
        epilog="Index ranges are START STOP like Python slices, counted from 0. "
        "Exit status: 0 on success, 1 if --compare found differences, 2 on errors.",
    )
    parser.add_argument("file", help="the CRG file")
    parser.add_argument("--version", action="version", version=f"pycrg {__version__}")
    parser.add_argument(
        "-f",
        "--figure",
        action="append",
        choices=["all", *_FIGURES],
        help="figure to show (repeatable; default: all, unless --peaks, --compare or --refpoints is given)",
    )
    parser.add_argument("--iu", nargs=2, type=int, metavar=("START", "STOP"), help="cross sections to show")
    parser.add_argument("--iv", nargs=2, type=int, metavar=("START", "STOP"), help="long sections to show")
    loading = parser.add_argument_group("loading")
    loading.add_argument("--no-modifiers", action="store_true", help="do not apply the file's modifiers")
    loading.add_argument("--check", action="store_true", help="run the OpenCRG consistency check first")
    analysis = parser.add_argument_group("analysis")
    analysis.add_argument("--peaks", action="store_true", help="find and show peaks (crg_peakfinder)")
    analysis.add_argument("--threshold", type=float, default=0.5, help="edge threshold of --peaks (default: 0.5)")
    analysis.add_argument("--window", type=int, default=3, help="median window of --peaks (default: 3)")
    analysis.add_argument(
        "--compare", metavar="OTHER", help="compare with the CRG file OTHER and show the differences (crg_isequal)"
    )
    analysis.add_argument(
        "--refpoints", metavar="POINTS", help="show the x y points of a text file with the reference line"
    )
    output = parser.add_argument_group("output")
    output.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="write the figures instead of showing them: a .pdf file gets all figures, "
        "a directory one file per figure, another file name one file per figure with a number",
    )
    output.add_argument("--format", default="png", help="image format for a directory --output (default: png)")
    output.add_argument("--dpi", type=float, default=100.0, help="resolution of written images (default: 100)")
    figure = parser.add_argument_group("figures")
    figure.add_argument("--portrait", action="store_true", help="portrait instead of landscape figures")
    figure.add_argument("--z-aspect", type=float, default=0.1, help="z aspect of 3D plots (default: 0.1)")
    figure.add_argument("--color-period", type=float, default=0.0, help="colour surfaces by z modulo this period")
    figure.add_argument("--light", action="store_true", help="light 3D surfaces")
    return parser


def _read_points(path: str) -> Any:
    """x and y of a text file with two (or more) columns, separated by blanks
    or commas; ``#`` starts a comment."""
    import numpy as np

    rows = []
    with open(path, encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            fields = line.split("#", 1)[0].replace(",", " ").split()
            if not fields:
                continue
            if len(fields) < 2:
                raise ValueError(f"{path}:{number}: expected x and y")
            rows.append((float(fields[0]), float(fields[1])))
    if not rows:
        raise ValueError(f"{path}: no points")
    return np.array(rows)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "figure"


def _save(figures: Sequence[Any], output: str, image_format: str, dpi: float, stem: str) -> list[Path]:
    path = Path(output)
    if path.suffix.lower() == ".pdf":
        from matplotlib.backends.backend_pdf import PdfPages

        path.parent.mkdir(parents=True, exist_ok=True)
        with PdfPages(path) as pdf:
            for fig in figures:
                pdf.savefig(fig, dpi=dpi)
        return [path]
    names = [f"{index:02d}-{_slug(fig.get_label())}" for index, fig in enumerate(figures, 1)]
    if path.is_dir() or output.endswith(("/", os.sep)) or not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        targets = [path / f"{stem}-{name}.{image_format}" for name in names]
    elif len(figures) == 1:
        path.parent.mkdir(parents=True, exist_ok=True)
        targets = [path]
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        targets = [path.with_name(f"{path.stem}-{name}{path.suffix}") for name in names]
    for fig, target in zip(figures, targets, strict=True):
        fig.savefig(target, dpi=dpi)
    return targets


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``pycrg-show`` with the arguments ``argv`` (default: ``sys.argv``)."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        import matplotlib
    except ImportError:
        print('pycrg-show: this command requires matplotlib: pip install "pycrg[plot]"', file=sys.stderr)
        return 2
    if args.output is not None:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backend_bases import FigureCanvasBase

    import pycrg
    import pycrg.plot as crgplot

    if args.output is None and plt.get_backend().lower() in _NON_INTERACTIVE_BACKENDS:
        print(
            f"pycrg-show: the matplotlib backend {plt.get_backend()!r} cannot display figures; "
            "write them to files with --output",
            file=sys.stderr,
        )
        return 2
    supported = FigureCanvasBase.get_supported_filetypes()
    if args.format not in supported:
        parser.error(f"unsupported --format {args.format!r}; choose from {', '.join(sorted(supported))}")
    try:
        options = crgplot.FigureOptions(
            orientation="portrait" if args.portrait else "landscape",
            z_aspect=args.z_aspect,
            color_period=args.color_period,
            light=args.light,
        )
    except ValueError as exc:
        parser.error(str(exc))

    iu = (args.iu[0], args.iu[1]) if args.iu else None
    iv = (args.iv[0], args.iv[1]) if args.iv else None
    selected = args.figure or ([] if args.peaks or args.compare or args.refpoints else ["all"])
    status = 0
    figures: list[Any] = []
    try:
        with pycrg.DataSet.open(args.file, apply_modifiers=not args.no_modifiers, check=args.check) as dataset:
            for name in dict.fromkeys(selected):
                if name == "all":
                    figures += crgplot.show(dataset, iu, iv, options=options)
                    continue
                function = getattr(crgplot, _FIGURES[name])
                if name in _WHOLE:
                    figures.append(function(dataset, options=options))
                elif name in _WITH_IV:
                    figures.append(function(dataset, iu, iv, options=options))
                else:
                    figures.append(function(dataset, iu, options=options))
            if args.refpoints:
                points = _read_points(args.refpoints)
                figures.append(crgplot.show_refpnts_and_refline(dataset, points, options=options))
            if args.peaks:
                peaks = pycrg.find_peaks(dataset, iu, iv, threshold=args.threshold, window=args.window)
                print(f"{len(peaks)} peak node(s) found")
                figures.append(crgplot.show_peaks(dataset, peaks, iu=iu, iv=iv, options=options))
            if args.compare:
                with pycrg.DataSet.open(args.compare, apply_modifiers=not args.no_modifiers, check=args.check) as other:
                    result = pycrg.compare(dataset, other)
                print("identical" if result.identical else "different", f"(max |dz| = {result.max_difference:g} m)")
                for message in result.errors:
                    print(f"error: {message}")
                for message in result.warnings:
                    print(f"warning: {message}")
                status = 0 if result.identical else 1
                figures.append(crgplot.show_isequal(result, options=options))
        if args.output is not None:
            for target in _save(figures, args.output, args.format, args.dpi, Path(args.file).stem):
                print(f"wrote {target}")
        else:
            plt.show()
    except (pycrg.OpenCRGError, OSError, ValueError) as exc:
        print(f"pycrg-show: {exc}", file=sys.stderr)
        return 2
    finally:
        for fig in figures:
            plt.close(fig)
    return status
