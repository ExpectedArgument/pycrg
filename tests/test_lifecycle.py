"""Ownership of native handles: closing, copying, finalizers, mem_release (findings 3, 4, 6)."""

import copy
import gc
import pickle
import subprocess
import sys
import textwrap
import warnings

import pytest

import pycrg
from pycrg import ContactPoint, DataSet, OpenCRGClosedError, RoadSurface


def test_handles_cannot_be_copied_or_pickled(straight):
    with RoadSurface.open(straight) as road:
        for obj in (road, road.dataset, road.contact_point):
            with pytest.raises(TypeError):
                copy.copy(obj)
            with pytest.raises(TypeError):
                copy.deepcopy(obj)
            with pytest.raises(TypeError):
                pickle.dumps(obj)


def test_handles_cannot_be_constructed_directly():
    with pytest.raises(TypeError):
        DataSet(1)
    with pytest.raises(TypeError):
        ContactPoint()


def test_closed_handle_does_not_read_a_reused_id(crg_txt):
    first = DataSet.open(crg_txt / "handmade_straight.crg")
    first_id = first.dataset_id
    first.close()
    second = DataSet.open(crg_txt / "handmade_circle.crg")
    assert second.dataset_id == first_id  # OpenCRG reuses the id
    with pytest.raises(OpenCRGClosedError):
        first.u_range()
    assert second.u_range() != (0.0, 22.0)
    second.close()


def test_identity_semantics(straight):
    a = DataSet.open(straight)
    b = DataSet.open(straight)
    assert a != b
    assert len({a, b, a}) == 2
    a.close()
    b.close()


def test_close_order_does_not_matter(straight):
    dataset = DataSet.open(straight)
    cp = dataset.create_contact_point()
    dataset.close()
    assert cp.closed
    cp.close()  # no-op
    with pytest.raises(OpenCRGClosedError):
        cp.uv_to_z(1.0, 0.0)

    dataset = DataSet.open(straight)
    cp = dataset.create_contact_point()
    cp.close()
    assert not dataset.closed
    dataset.close()
    dataset.close()


def test_closing_a_contact_point_keeps_other_contact_points(straight):
    with DataSet.open(straight) as dataset:
        cp1 = dataset.create_contact_point()
        cp2 = dataset.create_contact_point()
        cp1.close()
        cp3 = dataset.create_contact_point()  # may reuse the id of cp1
        assert cp2.uv_to_z(1.0, 0.0) == cp3.uv_to_z(1.0, 0.0)
        with pytest.raises(OpenCRGClosedError):
            cp1.uv_to_z(1.0, 0.0)


def test_mem_release_closes_everything(straight):
    dataset = DataSet.open(straight)
    cp = dataset.create_contact_point()
    road = RoadSurface.open(straight)

    pycrg.mem_release()

    assert dataset.closed and cp.closed and road.closed
    with pytest.raises(OpenCRGClosedError):
        dataset.u_range()
    with pytest.raises(OpenCRGClosedError):
        cp.uv_to_z(1.0, 0.0)
    with pytest.raises(OpenCRGClosedError):
        road.uv_to_z(1.0, 0.0)
    cp.close()
    dataset.close()
    road.close()

    # the library still works afterwards
    with DataSet.open(straight) as again:
        assert again.u_range() == (0.0, 22.0)


def test_context_managers(straight):
    with DataSet.open(straight) as dataset:
        with dataset.create_contact_point() as cp:
            assert cp.uv_to_z(1.0, 0.0) == pytest.approx(0.0111111, abs=1e-6)
        assert cp.closed
    assert dataset.closed
    with pytest.raises(OpenCRGClosedError), dataset:
        pass

    road = RoadSurface.open(straight)
    road.close()
    with pytest.raises(OpenCRGClosedError), road:
        pass


def test_unclosed_data_set_is_released_with_resource_warning(straight):
    with pytest.warns(ResourceWarning, match="unclosed pycrg.DataSet"):
        dataset = DataSet.open(straight)
        dataset_id = dataset.dataset_id
        del dataset
        gc.collect()
    assert dataset_id not in pycrg.api._open_datasets
    # the id is free again
    with DataSet.open(straight) as again:
        assert again.dataset_id == dataset_id


def test_many_unclosed_data_sets_do_not_accumulate(straight):
    ids = set()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        for _ in range(50):
            dataset = DataSet.open(straight)
            ids.add(dataset.dataset_id)
            del dataset
    assert len(ids) == 1
    assert not pycrg.api._open_datasets


def test_contact_point_keeps_data_set_alive(straight):
    cp = DataSet.open(straight).create_contact_point()
    gc.collect()
    assert cp.uv_to_z(1.0, 0.0) == pytest.approx(0.0111111, abs=1e-6)
    cp.dataset.close()


def test_unclosed_contact_points_are_released(straight):
    with DataSet.open(straight) as dataset:
        for _ in range(20):
            dataset.create_contact_point()
        gc.collect()
        assert not dataset._handle.contact_points
        cp = dataset.create_contact_point()
        assert cp.uv_to_z(1.0, 0.0) == pytest.approx(0.0111111, abs=1e-6)


def test_repr(straight):
    dataset = DataSet.open(straight)
    assert "handmade_straight.crg" in repr(dataset)
    dataset.close()
    assert "closed" in repr(dataset)


def test_interpreter_exit_with_open_handles(straight):
    code = textwrap.dedent(
        f"""
        import pycrg
        road = pycrg.RoadSurface.open({str(straight)!r})
        dataset = pycrg.DataSet.open({str(straight)!r})
        cp = dataset.create_contact_point()
        pycrg.set_message_level(pycrg.MSG_LEVEL_DEBUG)
        """
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
