from __future__ import annotations

from pathlib import Path

from pycrg import BORDER_MODE_EX_KEEP, CP_OPTION_BORDER_MODE_U, MOD_SCALE_Z, DataSet

if __name__ == "__main__":
    sample = Path(__file__).resolve().parents[2] / "tests" / "data" / "crg-txt" / "handmade_curved_banked_sloped.crg"

    # without applying the file's modifiers, to add an own one first
    with DataSet.open(sample, apply_modifiers=False) as dataset:
        print("check:", dataset.check())
        print("u/v increments:", dataset.increments())
        print("modifiers in the file:", dataset.header.modifiers)

        dataset.modifier_set_double(MOD_SCALE_Z, 2.0)
        print("MOD_SCALE_Z:", dataset.modifier_get_double(MOD_SCALE_Z))
        dataset.modifiers_apply()
        print(dataset.format_modifiers() or "(modifiers applied and removed)")

        with dataset.create_contact_point() as cp:
            cp.option_set_int(CP_OPTION_BORDER_MODE_U, BORDER_MODE_EX_KEEP)
            print("border mode u:", cp.option_get_int(CP_OPTION_BORDER_MODE_U))
            print("z at uv(10, 0.5):", cp.uv_to_z(10.0, 0.5))
            print("z before the start (border mode keep):", cp.uv_to_z(-5.0, 0.5))
