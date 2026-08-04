from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from merge_daml_docs_modules import merge_json_files, merge_stdlib_and_prim_modules  # noqa: E402


def test_merge_keeps_prim_move_content_for_shared_module_names() -> None:
    stdlib_modules = [
        {
            "md_name": "Prelude",
            "md_descr": ["stdlib prelude"],
            "md_anchor": "module-prelude-stdlib",
            "md_adts": [{"ADTDoc": {"ad_name": "Optional"}}],
            "md_classes": [{"cl_name": "Action"}],
            "md_functions": [{"fct_name": "assert"}],
            "md_instances": [{"id_type": "stdlib-inst"}],
        },
        {
            "md_name": "DA.Exception",
            "md_adts": [{"ADTDoc": {"ad_name": "SomeStdlibOnly"}}],
            "md_classes": [{"cl_name": "ActionThrow"}],
        },
        {
            "md_name": "DA.List",
            "md_functions": [{"fct_name": "map"}],
        },
    ]
    prim_modules = [
        {
            "md_name": "Prelude",
            "md_descr": None,
            "md_anchor": "module-prelude-prim",
            "md_adts": [{"ADTDoc": {"ad_name": "Bool"}}, {"ADTDoc": {"ad_name": "Int"}}],
            "md_classes": [{"cl_name": "Eq"}, {"cl_name": "NumericScale"}],
            "md_functions": [{"fct_name": "otherwise"}, {"fct_name": "map"}],
            "md_instances": [{"id_type": "prim-inst"}],
        },
        {
            "md_name": "DA.Exception",
            "md_adts": [
                {"ADTDoc": {"ad_name": "ArithmeticError"}},
                {"ADTDoc": {"ad_name": "AssertionFailed"}},
            ],
        },
        {
            "md_name": "DA.Stack",
            "md_adts": [{"ADTDoc": {"ad_name": "CallStack"}}],
        },
        {
            "md_name": "GHC.Tuple",
            "md_adts": [{"ADTDoc": {"ad_name": "Unit"}}],
        },
    ]

    combined = merge_stdlib_and_prim_modules(stdlib_modules, prim_modules)
    by_name = {module["md_name"]: module for module in combined}

    assert list(by_name) == ["Prelude", "DA.Exception", "DA.List", "DA.Stack", "GHC.Tuple"]

    prelude = by_name["Prelude"]
    assert prelude["md_descr"] == ["stdlib prelude"]
    assert prelude["md_anchor"] == "module-prelude-stdlib"
    assert [a["ADTDoc"]["ad_name"] for a in prelude["md_adts"]] == ["Optional", "Bool", "Int"]
    assert [c["cl_name"] for c in prelude["md_classes"]] == ["Action", "Eq", "NumericScale"]
    assert [f["fct_name"] for f in prelude["md_functions"]] == ["assert", "otherwise", "map"]
    assert prelude["md_instances"] == [{"id_type": "stdlib-inst"}, {"id_type": "prim-inst"}]

    exception = by_name["DA.Exception"]
    assert [a["ADTDoc"]["ad_name"] for a in exception["md_adts"]] == [
        "SomeStdlibOnly",
        "ArithmeticError",
        "AssertionFailed",
    ]
    assert [c["cl_name"] for c in exception["md_classes"]] == ["ActionThrow"]

    stack = by_name["DA.Stack"]
    assert [a["ADTDoc"]["ad_name"] for a in stack["md_adts"]] == ["CallStack"]


def test_merge_json_files_roundtrip(tmp_path: Path) -> None:
    stdlib_path = tmp_path / "stdlib.json"
    prim_path = tmp_path / "prim.json"
    out_path = tmp_path / "base.json"
    stdlib_path.write_text(
        json.dumps([{"md_name": "Prelude", "md_adts": [{"ADTDoc": {"ad_name": "Optional"}}]}]) + "\n",
        encoding="utf-8",
    )
    prim_path.write_text(
        json.dumps([{"md_name": "Prelude", "md_adts": [{"ADTDoc": {"ad_name": "Bool"}}]}]) + "\n",
        encoding="utf-8",
    )

    count = merge_json_files(stdlib_path, prim_path, out_path)
    assert count == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert [a["ADTDoc"]["ad_name"] for a in payload[0]["md_adts"]] == ["Optional", "Bool"]
