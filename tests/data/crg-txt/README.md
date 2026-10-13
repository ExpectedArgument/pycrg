# OpenCRG sample files

The `*.crg` files in this directory are the text samples of the ASAM OpenCRG
project, copied unchanged from `crg-txt/` of https://github.com/asam-ev/OpenCRG
(commit `4b747acf9a25f02f329eb1e640836cbd9a35952f`). They are distributed under
the Apache License 2.0; see their `$CT` sections and the `LICENSE` and `NOTICE`
files of the vendored OpenCRG sources in `src/pycrg/vendor/opencrg/`.

The directory keeps the upstream name `crg-txt`, since the file references in
`fileref*.crg` point to `../crg-txt/handmade_curved_banked_sloped.crg`.
`testOptionBorderMode.crg` refers to a file that does not exist upstream
(`handmade_sloped_opt.crg`), so it cannot be loaded.
