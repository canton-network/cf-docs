from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .compiler import (
    CompilationTarget,
    ConditionPredicate,
    GeneratedOutputDrift,
    assert_generated_output,
    compile_page_variants,
    write_generated_output,
)
from .model import IfVersionDirective
from .parser import load_registry, parse_page
from .release import (
    ReleaseEvaluator,
    ReleaseEvidence,
    ReleaseResolutionError,
    ReleaseTarget,
    Version,
    load_deployed_targets,
)
from .source import GitHubClient, SourceResolutionError, SourceResolver


CF_DOCS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = CF_DOCS_ROOT / "config" / "snippet-repositories.json"
DEFAULT_DASHBOARD = CF_DOCS_ROOT / "config" / "repo-version-config.json"
DEFAULT_PREVIEW_ROOT = CF_DOCS_ROOT / ".internal" / "snippet-preview"
DEFAULT_EVIDENCE_ROOT = CF_DOCS_ROOT / "config" / "snippet-evidence"


def _local_checkouts(values: list[str]) -> dict[str, Path]:
    checkouts: dict[str, Path] = {}
    for value in values:
        repository, separator, raw_path = value.partition("=")
        if not separator or not repository or not raw_path:
            raise ReleaseResolutionError(
                f"Local source must be OWNER/REPO=PATH, got {value!r}"
            )
        if repository in checkouts:
            raise ReleaseResolutionError(
                f"Local source was supplied more than once for {repository}"
            )
        checkouts[repository] = Path(raw_path).expanduser().resolve()
    return checkouts


def _page_repositories(
    text: str, page: Path, repositories: dict[str, dict[str, Any]]
) -> set[str]:
    parsed = parse_page(
        text,
        path=page,
        repositories=repositories,
        allow_local=True,
    )
    return {condition.repository for condition in parsed.conditions}


def _display_page(page: Path) -> Path:
    try:
        return page.resolve().relative_to(CF_DOCS_ROOT.resolve())
    except ValueError:
        return page


def _condition_repository(condition_repositories: set[str]) -> str:
    if len(condition_repositories) != 1:
        rendered = ", ".join(sorted(condition_repositories)) or "none"
        raise ReleaseResolutionError(
            "Release ranges and --deployed require exactly one conditional repository "
            f"in the page; found {rendered}"
        )
    return next(iter(condition_repositories))


def _release_targets(
    args: argparse.Namespace,
    *,
    evaluator: ReleaseEvaluator,
    condition_repositories: set[str],
) -> list[ReleaseTarget]:
    targets = [ReleaseTarget.exact(value) for value in args.release]
    for raw_range in args.releases:
        start_raw, separator, end_raw = raw_range.partition("..")
        if not separator:
            raise ReleaseResolutionError(
                f"Release range must be START..END, got {raw_range!r}"
            )
        repository = _condition_repository(condition_repositories)
        targets.extend(
            evaluator.published_targets_between(
                repository, Version.parse(start_raw), Version.parse(end_raw)
            )
        )
    if args.deployed:
        repository = _condition_repository(condition_repositories)
        targets.extend(load_deployed_targets(args.dashboard, repository=repository))
    if args.candidate:
        targets.append(ReleaseTarget.candidate_preview())
    if not targets:
        if not condition_repositories:
            return []
        raise ReleaseResolutionError(
            "Select at least one --release, --releases START..END, --deployed, or --candidate"
        )
    deduplicated: list[ReleaseTarget] = []
    for target in targets:
        if target not in deduplicated:
            deduplicated.append(target)
    return deduplicated


def _target_label(target: ReleaseTarget) -> str:
    if target.version is None:
        return target.label
    version = str(target.version)
    return target.label if target.label == version else f"{target.label} ({version})"


def _compilation_targets(
    targets: list[ReleaseTarget], evaluator: ReleaseEvaluator
) -> tuple[CompilationTarget, ...]:
    def predicate(target: ReleaseTarget) -> ConditionPredicate:
        def contains(condition: IfVersionDirective) -> bool:
            return evaluator.contains(condition, target)

        return contains

    return tuple(
        CompilationTarget(
            label=_target_label(target),
            condition_contains=predicate(target),
            production=not target.candidate,
        )
        for target in targets
    )


def _evidence_payload(
    page: Path, evidence: tuple[ReleaseEvidence, ...]
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for item in evidence:
        record = asdict(item)
        target = item.target
        record["target"] = {
            "label": target.label,
            "version": str(target.version) if target.version else None,
            "candidate": target.candidate,
        }
        records.append(record)
    return {"sourcePage": str(page), "conditions": records}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _production_evidence_path(page: Path) -> Path:
    try:
        relative = page.resolve().relative_to((CF_DOCS_ROOT / "docs-main").resolve())
    except ValueError as error:
        raise ReleaseResolutionError(
            f"Production authored page must be under {CF_DOCS_ROOT / 'docs-main'}: {page}"
        ) from error
    return DEFAULT_EVIDENCE_ROOT / relative.with_suffix(".json")


def _add_target_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--release",
        action="append",
        default=[],
        metavar="X.Y.Z",
        help="Render an exact release; repeat to compare releases.",
    )
    parser.add_argument(
        "--releases",
        action="append",
        default=[],
        metavar="START..END",
        help="Render every jointly published release in an inclusive range.",
    )
    parser.add_argument(
        "--deployed",
        action="store_true",
        help="Render DevNet, TestNet, and MainNet versions from the checked-in dashboard.",
    )
    parser.add_argument(
        "--candidate",
        action="store_true",
        help="Also render candidate PR heads inferred from IfVersion declarations.",
    )
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile and preview inline release-aware snippets"
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview = subparsers.add_parser("preview", help="Render a local comparison page")
    preview.add_argument("--page", type=Path, required=True)
    preview.add_argument("--output", type=Path)
    preview.add_argument(
        "--source-dir",
        action="append",
        default=[],
        metavar="OWNER/REPO=PATH",
        help="Resolve local:// references from a matching git checkout.",
    )
    _add_target_arguments(preview)

    for name in ("generate", "check"):
        command = subparsers.add_parser(
            name,
            help=(
                "Write the sibling production MDX page"
                if name == "generate"
                else "Fail when sibling production MDX or evidence is stale"
            ),
        )
        command.add_argument("--page", type=Path, required=True)
        _add_target_arguments(command)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repositories = load_registry(args.registry)
        page = args.page.expanduser().resolve()
        text = page.read_text(encoding="utf-8")
        condition_repositories = _page_repositories(text, page, repositories)
        github = GitHubClient()
        evaluator = ReleaseEvaluator(github, repositories)
        targets = _release_targets(
            args,
            evaluator=evaluator,
            condition_repositories=condition_repositories,
        )
        checkouts = _local_checkouts(getattr(args, "source_dir", []))
        source_resolver = SourceResolver(
            github,
            repositories=set(repositories),
            local_checkouts=checkouts,
            allow_local=args.command == "preview",
        )
        display_page = _display_page(page)
        compilation_targets = _compilation_targets(targets, evaluator)
        if not compilation_targets:
            compilation_targets = (
                CompilationTarget(
                    label="Pinned sources",
                    condition_contains=lambda _: False,
                    production=True,
                ),
            )
        compiled = compile_page_variants(
            text,
            page_path=display_page,
            repositories=repositories,
            source_resolver=source_resolver,
            targets=compilation_targets,
            allow_local=args.command == "preview",
        )
        evidence = _evidence_payload(display_page, evaluator.evidence)
        if args.command == "preview":
            output = args.output or DEFAULT_PREVIEW_ROOT / f"{page.stem}.mdx"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(compiled, encoding="utf-8")
            evidence_path = output.with_suffix(".evidence.json")
            _write_json(evidence_path, evidence)
            print(f"Preview:  {output}")
            print(f"Evidence: {evidence_path}")
            return 0

        evidence_path = _production_evidence_path(page)
        if args.command == "generate":
            output = write_generated_output(page, compiled)
            _write_json(evidence_path, evidence)
            print(f"Generated: {output}")
            print(f"Evidence:  {evidence_path}")
            return 0

        assert_generated_output(page, compiled)
        expected_evidence = json.dumps(evidence, indent=2) + "\n"
        if (
            not evidence_path.is_file()
            or evidence_path.read_text(encoding="utf-8") != expected_evidence
        ):
            raise GeneratedOutputDrift(
                f"Release evidence is stale for {page}: run `npm run snippets:generate -- --page {page} --deployed`"
            )
        print(f"Generated output and evidence are current for {page}")
        return 0
    except (
        GeneratedOutputDrift,
        OSError,
        ReleaseResolutionError,
        SourceResolutionError,
        ValueError,
    ) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
