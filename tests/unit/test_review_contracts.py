from dataclasses import replace
from string import Formatter

import pytest

from tum_mcp.course.review import loop, registry, runner
from tum_mcp.course.review.items import ReviewItem
from tum_mcp.course.review.ledger import Verdict


@pytest.mark.parametrize("check", registry.checks().values(), ids=list(registry.checks()))
def test_a_changed_check_version_invalidates_an_unchanged_content_verdict(
    check: registry.Check,
) -> None:
    value = {"title": "Synthetic teaching"}
    item = ReviewItem("study/topic", check.profiles[0], "Topic", value)
    verdict = Verdict(
        verdict="pass",
        method="read",
        round=1,
        provenance="fresh",
        fingerprint=loop.covered(item, ("*",), check.id),
        version=check.version,
    )
    assert loop.is_current(verdict, check, item)
    assert not loop.is_current(verdict, replace(check, version=check.version + 1), item)


@pytest.mark.parametrize(
    ("template", "fields"),
    [
        (runner.PROMPT, {"packet"}),
        (runner.REPAIR_PROMPT, {"packet", "answer", "problems"}),
        (runner.PLAN_PROMPT, {"packet"}),
    ],
    ids=["review", "repair", "plan"],
)
def test_checker_templates_accept_only_the_fields_supplied_by_the_runner(
    template: str, fields: set[str]
) -> None:
    parsed = {field for _, field, _, _ in Formatter().parse(template) if field is not None}
    assert parsed == fields
    _ = template.format(**dict.fromkeys(fields, "synthetic-packet.json"))
