from __future__ import annotations

from pathlib import Path

from pycrg import CP_OPTION_BORDER_MODE_U, DataSet, MOD_SCALE_Z


if __name__ == "__main__":
    sample = Path(__file__).resolve().parents[2] / "tests" / "data" / "sample.crg"

    dataset = DataSet.open(str(sample))
    print("check:", dataset.check())
    print("u/v increments:", dataset.increments())

    dataset.modifier_set_double(MOD_SCALE_Z, 1.0)
    print("MOD_SCALE_Z:", dataset.modifier_get_double(MOD_SCALE_Z))

    cp = dataset.create_contact_point()
    cp.option_set_int(CP_OPTION_BORDER_MODE_U, 2)
    print("border mode u:", cp.option_get_int(CP_OPTION_BORDER_MODE_U))

    print("z at uv(0,0):", cp.uv_to_z(0.0, 0.0))

    cp.close()
    dataset.close()
