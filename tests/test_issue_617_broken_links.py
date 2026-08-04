from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_issue_617_authored_broken_links_do_not_regress() -> None:
    configuration_guide = (
        REPO_ROOT / "docs-main/global-synchronizer/reference/canton-configuration-guide.mdx"
    ).read_text(encoding="utf-8")
    token_standard = (
        REPO_ROOT / "docs-main/appdev/deep-dives/token-standard.mdx"
    ).read_text(encoding="utf-8")
    scan_examples = (
        REPO_ROOT
        / "docs-main/snippets/networkvars/sdks-tools/api-reference/splice-scan-bulk-data-api-1.mdx"
    ).read_text(encoding="utf-8")

    assert "/reference/scala/" not in configuration_guide
    assert "[|gsf_scan_url|" not in scan_examples
    assert "](|gsf_scan_url|" not in scan_examples

    expected_operation_routes = {
        "/reference/splice-token-metadata-service/get-registrymetadatav1info",
        "/reference/splice-transfer-instruction-api/post-registrytransfer-instructionv1transfer-factory",
        "/reference/splice-allocation-api/post-registryallocationsv1:allocationidchoice-contextsexecute-transfer",
        "/reference/splice-allocation-instruction-api/post-registryallocation-instructionv1allocation-factory",
    }
    for route in expected_operation_routes:
        assert f"]({route})" in token_standard


def test_issue_617_generated_openapi_has_no_unpublished_schema_links() -> None:
    managed_openapi_root = REPO_ROOT / "docs-main/openapi/splice"

    offenders = [
        path.relative_to(REPO_ROOT)
        for path in managed_openapi_root.rglob("*.yaml")
        if "common-external.yaml" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
