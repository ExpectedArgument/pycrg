"""The pycrg-show command (python -m pycrg.plot)."""

import re
import subprocess
import sys

import pytest

import pycrg

pytest.importorskip("pycrg.plot")  # requires matplotlib

from pycrg._cli import main

CURVED = "handmade_curved.crg"


def pdf_pages(path):
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", path.read_bytes()))


def test_one_file_per_figure(plt, crg_txt, tmp_path, capsys):
    out = tmp_path / "figures"
    assert main([str(crg_txt / CURVED), "--output", f"{out}/"]) == 0
    names = sorted(path.name for path in out.iterdir())
    assert names == [
        "handmade_curved-01-crg-reference-line-map.png",
        "handmade_curved-02-crg-elevation-grid-cuts-and-limits.png",
        "handmade_curved-03-crg-road-surface.png",
        "handmade_curved-04-crg-information.png",
    ]
    assert capsys.readouterr().out.count("wrote ") == 4
    assert plt.get_fignums() == []  # the figures are closed


def test_pdf_with_selected_figures(plt, crg_txt, tmp_path):
    pdf = tmp_path / "road.pdf"
    status = main(
        [str(crg_txt / CURVED), "-f", "info", "-f", "road-surface", "-f", "info", "--iu", "2", "10", "-o", str(pdf)]
    )
    assert status == 0
    assert pdf_pages(pdf) == 2  # repeated figures are drawn once


def test_numbered_files_and_formats(plt, crg_txt, tmp_path):
    single = tmp_path / "info.svg"
    assert main([str(crg_txt / CURVED), "-f", "info", "-o", str(single)]) == 0
    assert single.read_text(encoding="utf-8").lstrip().startswith("<?xml")
    numbered = tmp_path / "sub" / "fig.png"
    assert main([str(crg_txt / CURVED), "-f", "refline-map", "-f", "elgrid-cuts", "-o", str(numbered)]) == 0
    assert sorted(path.name for path in numbered.parent.iterdir()) == [
        "fig-01-crg-reference-line-map.png",
        "fig-02-crg-elevation-grid-cuts-and-limits.png",
    ]
    out = tmp_path / "pdfs"
    assert (
        main([str(crg_txt / CURVED), "-f", "elgrid-surface", "--iv", "1", "5", "--format", "pdf", "-o", str(out)]) == 0
    )
    assert [path.suffix for path in out.iterdir()] == [".pdf"]
    with pytest.raises(SystemExit) as excinfo:
        main([str(crg_txt / CURVED), "--format", "bmpx", "-o", str(out)])
    assert excinfo.value.code == 2


def test_figure_options(plt, crg_txt, tmp_path):
    options = ["--portrait", "--z-aspect", "1", "--color-period", "0.01", "--light", "--no-modifiers", "--check"]
    assert main([str(crg_txt / CURVED), "-f", "road-surface", *options, "-o", str(tmp_path / "a.png")]) == 0
    with pytest.raises(SystemExit) as excinfo:
        main([str(crg_txt / CURVED), "--z-aspect", "0", "-o", str(tmp_path / "b.png")])
    assert excinfo.value.code == 2


def test_compare_exit_status(plt, write_road, numpy, tmp_path, capsys):
    z = numpy.zeros((41, 7))
    changed = z.copy()
    changed[20, 3] = 0.2
    first = write_road("first.crg", z=z, mods={})
    second = write_road("second.crg", z=changed, mods={})
    assert main([str(first), "--compare", str(first), "-o", str(tmp_path / "same.png")]) == 0
    assert capsys.readouterr().out.startswith("identical")
    assert main([str(first), "--compare", str(second), "-o", str(tmp_path / "different.png")]) == 1
    output = capsys.readouterr().out
    assert output.startswith("different (max |dz| = 0.2 m)")
    assert (tmp_path / "different.png").exists()


def test_peaks_and_reference_points(plt, write_road, numpy, tmp_path, capsys):
    z = numpy.zeros((60, 21))
    z[30, 8] = 0.4
    road = write_road(z=z, nu=60, nv=21, mods={})
    assert main([str(road), "--peaks", "--window", "2", "-o", str(tmp_path / "peaks.png")]) == 0
    assert "1 peak node(s) found" in capsys.readouterr().out
    points = tmp_path / "points.txt"
    points.write_text("# x, y\n0.0, 0.0\n5.0 0.1  # a comment\n\n10.0,-0.1\n", encoding="utf-8")
    assert main([str(road), "--refpoints", str(points), "-o", str(tmp_path / "points.png")]) == 0
    bad = tmp_path / "bad.txt"
    bad.write_text("1.0\n", encoding="utf-8")
    assert main([str(road), "--refpoints", str(bad), "-o", str(tmp_path / "bad.png")]) == 2
    assert "expected x and y" in capsys.readouterr().err


def test_errors(plt, crg_txt, tmp_path, capsys):
    assert main([str(tmp_path / "missing.crg"), "-o", str(tmp_path / "x.png")]) == 2
    assert "No such file" in capsys.readouterr().err
    assert main([str(crg_txt / CURVED), "--iu", "5", "3", "-o", str(tmp_path / "x.png")]) == 2
    assert "illegal iu index range" in capsys.readouterr().err
    assert main([str(crg_txt / "testOptionBorderMode.crg"), "-o", str(tmp_path / "x.png")]) == 2
    assert "Failed to load CRG file" in capsys.readouterr().err
    assert not (tmp_path / "x.png").exists()


def test_display_needs_an_interactive_backend(plt, crg_txt, capsys):
    assert main([str(crg_txt / CURVED)]) == 2
    assert "cannot display figures" in capsys.readouterr().err


def test_version_and_module(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"pycrg {pycrg.__version__}"
    result = subprocess.run([sys.executable, "-m", "pycrg.plot", "--help"], capture_output=True, text=True, check=True)
    assert result.stdout.startswith("usage: pycrg-show")
