from types import SimpleNamespace

from manuskript.functions import spellchecker


def test_language_tool_match_uses_modern_attribute_names(monkeypatch):
    monkeypatch.setattr(spellchecker, "use_language_check", False)
    match = SimpleNamespace(
        error_length=4,
        rule_issue_type="grammar",
    )

    assert spellchecker.get_languagetool_match_errorLength(match) == 4
    assert (
        spellchecker.get_languagetool_match_ruleIssueType(match)
        == "grammar"
    )


def test_language_tool_match_retains_legacy_attribute_support(
    monkeypatch,
):
    monkeypatch.setattr(spellchecker, "use_language_check", False)
    match = SimpleNamespace(
        errorLength=3,
        ruleIssueType="misspelling",
    )

    assert spellchecker.get_languagetool_match_errorLength(match) == 3
    assert (
        spellchecker.get_languagetool_match_ruleIssueType(match)
        == "misspelling"
    )
