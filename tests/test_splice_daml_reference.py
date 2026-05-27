from __future__ import annotations

import io
import tarfile
from pathlib import Path

import scripts.generate_splice_daml_reference as splice_daml_reference


def write_mdx(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: \"{title}\"\n---\n", encoding="utf-8")


def add_tar_file(handle: tarfile.TarFile, name: str, data: bytes = b"content") -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    handle.addfile(info, io.BytesIO(data))


def test_dar_members_from_archive_prefers_current_dar(tmp_path: Path) -> None:
    archive = tmp_path / "splice-node.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        add_tar_file(handle, "bundle/dars/splice-util-0.6.4.dar")
        add_tar_file(handle, "bundle/dars/splice-util-current.dar")
        add_tar_file(handle, "bundle/dars/splice-wallet-0.6.4.dar")

    assert splice_daml_reference.dar_members_from_archive(archive) == {
        "splice-util": "bundle/dars/splice-util-current.dar",
        "splice-wallet": "bundle/dars/splice-wallet-0.6.4.dar",
    }


def test_dependency_include_dirs_resolves_nested_package_ids(tmp_path: Path) -> None:
    base = tmp_path / "packages"
    dependency = splice_daml_reference.PackageInfo(
        family="dependency",
        package_name="dependency",
        package_id="dependency-1.0.0",
        package_root=base / "dependency",
        exposed_modules=["Dependency"],
        depends=[],
    )
    parent = splice_daml_reference.PackageInfo(
        family="parent",
        package_name="parent",
        package_id="parent-1.0.0",
        package_root=base / "parent",
        exposed_modules=["Parent"],
        depends=["dependency-1.0.0"],
    )

    assert splice_daml_reference.dependency_include_dirs(
        info=parent,
        package_index={dependency.package_id: dependency, parent.package_id: parent},
    ) == [dependency.package_root]


def test_update_docs_navigation_replaces_product_nested_splice_group(tmp_path: Path) -> None:
    docs_json = tmp_path / "docs-main" / "docs.json"
    output_root = tmp_path / "docs-main" / "sdks-tools" / "api-reference" / "splice-daml"
    write_mdx(output_root / "splice-util" / "index.mdx", "splice-util")
    write_mdx(output_root / "splice-util" / "splice-util.mdx", "Splice.Util")
    write_mdx(output_root / "splice-token-standard-test" / "index.mdx", "splice-token-standard-test")
    docs_json.parent.mkdir(parents=True, exist_ok=True)
    docs_json.write_text(
        """
{
  "navigation": {
    "products": [
      {
        "product": "SDKs and Tools",
        "pages": [
          {
            "group": "API Overview",
            "pages": [
              {
                "group": "Splice APIs",
                "pages": [
                  "sdks-tools/api-reference/splice-daml-apis",
                  {
                    "group": "Splice Daml Packages",
                    "pages": ["old/ref"]
                  }
                ]
              }
            ]
          }
        ]
      },
      {
        "product": "API Reference",
        "pages": [
          {
            "group": "Splice APIs",
            "pages": [
              "sdks-tools/api-reference/splice-daml-apis"
            ]
          }
        ]
      }
    ]
  }
}
""".lstrip(),
        encoding="utf-8",
    )

    splice_daml_reference.update_docs_navigation(
        docs_json_path=docs_json,
        product_label="API Reference",
        parent_groups=["Splice APIs"],
        nav_group_label="Splice Daml Packages",
        output_root=output_root,
        family_order=["splice-util", "splice-token-standard-test"],
    )

    payload = splice_daml_reference.load_json(docs_json)
    sdk_pages = payload["navigation"]["products"][0]["pages"][0]["pages"][0]["pages"]
    assert all(not isinstance(item, dict) or item.get("group") != "Splice Daml Packages" for item in sdk_pages)
    splice_pages = payload["navigation"]["products"][1]["pages"][0]["pages"]
    package_group = next(item for item in splice_pages if isinstance(item, dict) and item["group"] == "Splice Daml Packages")
    assert package_group == {
        "group": "Splice Daml Packages",
        "pages": [
            {
                "group": "splice-util",
                "pages": [
                    "sdks-tools/api-reference/splice-daml/splice-util/index",
                    "sdks-tools/api-reference/splice-daml/splice-util/splice-util",
                ],
            },
            {
                "group": "splice-token-standard-test",
                "pages": [
                    "sdks-tools/api-reference/splice-daml/splice-token-standard-test/index",
                ],
            },
        ],
    }
