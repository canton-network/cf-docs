from __future__ import annotations

import pytest

from scripts.snippets.model import (
    IfVersionAttributeRule,
    IfVersionAttributeValidation,
    IfVersionTag,
)
from scripts.snippets.registry import (
    RepositoryConfig,
    RepositoryRegistry,
    RepositoryVisibility,
)
from scripts.snippets.syntax import parse_if_version_tags
from scripts.snippets.validation import validate_if_version_attributes

REGISTRY = RepositoryRegistry(
    (
        RepositoryConfig(
            name="canton-network/splice",
            url="https://github.com/canton-network/splice",
            default_branch="main",
            visibility=RepositoryVisibility.PUBLIC,
        ),
    )
)


def validate(text: str) -> IfVersionAttributeValidation:
    tag = parse_if_version_tags(text)[0]
    assert isinstance(tag, IfVersionTag)
    return validate_if_version_attributes(tag, REGISTRY)


def test_builds_condition_from_valid_attributes() -> None:
    result = validate(
        '<IfVersion repository="https://github.com/canton-network/splice" '
        "containsPullRequest={6123}>"
    )

    assert result.issues == ()
    assert result.condition is not None
    assert result.condition.repository == "canton-network/splice"
    assert result.condition.contains_pull_request == 6123


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        (
            (
                '<IfVersion repository="https://github.com/canton-network/splice" '
                'containsPullRequest={6123} extra="value">'
            ),
            IfVersionAttributeRule.UNKNOWN_ATTRIBUTE,
        ),
        (
            (
                '<IfVersion repository="canton-network/splice" '
                "containsPullRequest={6123}>"
            ),
            IfVersionAttributeRule.INVALID_REPOSITORY,
        ),
        (
            (
                '<IfVersion repository="https://github.com/unknown/repository" '
                "containsPullRequest={6123}>"
            ),
            IfVersionAttributeRule.UNREGISTERED_REPOSITORY,
        ),
        (
            '<IfVersion repository="https://github.com/canton-network/splice">',
            IfVersionAttributeRule.INVALID_PULL_REQUEST,
        ),
        (
            (
                '<IfVersion repository="https://github.com/canton-network/splice" '
                'containsPullRequest="6123">'
            ),
            IfVersionAttributeRule.INVALID_PULL_REQUEST,
        ),
        (
            (
                '<IfVersion repository="https://github.com/canton-network/splice" '
                "containsPullRequest={0}>"
            ),
            IfVersionAttributeRule.INVALID_PULL_REQUEST,
        ),
    ],
)
def test_rejects_invalid_condition_attributes(
    text: str, rule: IfVersionAttributeRule
) -> None:
    assert rule in {issue.rule for issue in validate(text).issues}
