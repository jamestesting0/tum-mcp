import json

import pytest
from skill_lab import LabError, models
from skill_lab.models import ModelSpec


def write_cache(home, slugs):
    cache = home / ".codex" / "models_cache.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": slug,
                        "supported_reasoning_levels": [
                            {"effort": e} for e in ("low", "high", "xhigh", "ultra")
                        ],
                    }
                    for slug in slugs
                ]
            }
        )
    )


def test_bare_host_names_expand_to_the_default_author():
    assert str(ModelSpec.parse("codex")) == "codex:gpt-6.1-terra:xhigh"
    assert str(ModelSpec.parse("claude")) == "claude:opus:medium"


def test_parse_round_trips_and_rejects_bad_specs():
    spec = ModelSpec.parse("codex:gpt-6.1-sol:xhigh")
    assert (spec.host, spec.model, spec.effort) == ("codex", "gpt-6.1-sol", "xhigh")
    assert ModelSpec.from_dict(spec.as_dict()) == spec
    for bad in ("codex:gpt", "other:m:high", "claude::high"):
        with pytest.raises(LabError):
            ModelSpec.parse(bad)


def test_claude_validation_accepts_aliases_and_full_names(tmp_path):
    for text in ("claude:opus:xhigh", "claude:claude-opus-5-5:xhigh"):
        models.validate(ModelSpec.parse(text), role="judge", profile_home=tmp_path)
    with pytest.raises(LabError):
        models.validate(ModelSpec.parse("claude:gpt-6:high"), role="author", profile_home=tmp_path)
    with pytest.raises(LabError):
        models.validate(ModelSpec.parse("claude:opus:ultra"), role="author", profile_home=tmp_path)


def test_codex_validation_uses_the_profile_model_list(tmp_path):
    write_cache(tmp_path, ["gpt-6.1-sol"])
    models.validate(ModelSpec.parse("codex:gpt-6.1-sol:xhigh"), role="judge", profile_home=tmp_path)
    models.validate(
        ModelSpec.parse("codex:gpt-6.1-sol:ultra"), role="author", profile_home=tmp_path
    )
    with pytest.raises(LabError, match="delegates"):
        models.validate(
            ModelSpec.parse("codex:gpt-6.1-sol:ultra"), role="judge", profile_home=tmp_path
        )
    with pytest.raises(LabError, match="not in the model list"):
        models.validate(ModelSpec.parse("codex:gpt-x:high"), role="author", profile_home=tmp_path)
    with pytest.raises(LabError, match="supports efforts"):
        models.validate(
            ModelSpec.parse("codex:gpt-6.1-sol:max"), role="author", profile_home=tmp_path
        )


def test_reported_model_matching():
    alias = ModelSpec.parse("claude:opus:high")
    assert models.reported_matches(alias, "claude-opus-5-5") is True
    assert models.reported_matches(alias, "claude-sonnet-5") is False
    assert models.reported_matches(alias, None) is None
    exact = ModelSpec.parse("codex:gpt-6.1-sol:high")
    assert models.reported_matches(exact, "gpt-6.1-sol") is True
    assert models.reported_matches(exact, "gpt-6.1-terra") is False
