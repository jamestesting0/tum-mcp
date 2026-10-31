from skill_lab import safety, shim

SKILL = "src/tum_mcp/bundled/skills/prepare-study/SKILL.md"
PATCH = (
    f"diff --git a/{SKILL} b/{SKILL}\n"
    + """--- a/src/tum_mcp/bundled/skills/prepare-study/SKILL.md
+++ b/src/tum_mcp/bundled/skills/prepare-study/SKILL.md
@@ -1 +1 @@
-old
+new
diff --git a/src/tum_mcp/moodle/service.py b/src/tum_mcp/moodle/service.py
--- a/src/tum_mcp/moodle/service.py
+++ b/src/tum_mcp/moodle/service.py
@@ -1 +1 @@
-a
+b
"""
)


def test_patch_paths_and_guard():
    touched = safety.patch_paths(PATCH)
    assert touched == [
        "src/tum_mcp/bundled/skills/prepare-study/SKILL.md",
        "src/tum_mcp/moodle/service.py",
    ]
    assert safety.guarded(touched) == ["src/tum_mcp/moodle/service.py"]
    for path in ("skill-lab/skill_lab/runs.py", "src/tum_mcp/client_rendering.py", "AGENTS.md"):
        assert safety.guarded([path]) == [path]
    assert safety.guarded(["src/tum_mcp/study_report.py"]) == []


def test_shim_refuses_account_and_publishing_commands():
    for arguments in (["login"], ["logout"], ["setup"], ["study", "publish"], ["serve"]):
        assert shim.refusal(arguments)
    for arguments in (["study", "report", "."], ["discover"], []):
        assert shim.refusal(arguments) is None


def test_credential_scan(tmp_path):
    assert safety.credential_hits("Authorization: Bearer " + "a" * 30)
    assert safety.credential_hits('{"password": "hunter22"}')
    assert safety.credential_hits("MoodleSession=abcdef1234567890")
    assert not safety.credential_hits("The lecture covers Bayesian networks.")
    (tmp_path / "notes.txt").write_text("cookie _shibsession_x=0123456789abcdef")
    (tmp_path / "slides.pdf").write_bytes(b"Bearer " + b"b" * 40)
    hits = safety.scan_tree(tmp_path)
    assert len(hits) == 1 and hits[0].startswith("notes.txt")


def test_claude_redaction_hides_personal_tool_results_only():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "1", "name": "mcp__tum__tumonline_list_studies"},
                    {"type": "tool_use", "id": "2", "name": "mcp__tum__moodle_list_materials"},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "1", "content": "Private programme"},
                ]
            },
            "tool_use_result": {"studies": ["Private programme"]},
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "2", "content": "Lecture 1"}]
            },
        },
    ]
    redacted = safety.redact_claude(events)
    first = redacted[1]["message"]["content"][0]["content"]
    assert first["redacted"] is True and "Private" not in str(redacted[1])
    assert redacted[2]["message"]["content"][0]["content"] == "Lecture 1"


def test_redaction_also_scrubs_the_agents_echo_of_personal_results():
    studies = '{"studies": [{"name": "Informatics", "degree": "Master of Science"}]}'
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "1", "name": "mcp__tum__tumonline_list_studies"}
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "1",
                        "content": [{"type": "text", "text": studies}],
                    }
                ]
            },
        },
        {"type": "result", "result": "You study Informatics (Master of Science); status unknown."},
    ]
    redacted = safety.redact_claude(events)
    final = redacted[2]["result"]
    assert "Informatics" not in final and "Master of Science" not in final
    assert final.endswith("status unknown.")
    codex = [
        {
            "type": "item.completed",
            "item": {
                "type": "mcp_tool_call",
                "tool": "tumonline_list_courses",
                "result": {"courses": ["Course 4711 Alpha"]},
            },
        },
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Found Course 4711 Alpha."},
        },
    ]
    assert "Alpha" not in safety.redact_codex(codex)[1]["item"]["text"]


def test_codex_redaction():
    events = [
        {
            "type": "item.completed",
            "item": {"type": "mcp_tool_call", "tool": "zulip_read_topic", "result": "hi Anna"},
        },
        {
            "type": "item.completed",
            "item": {"type": "mcp_tool_call", "tool": "moodle_list_courses", "result": "AI"},
        },
    ]
    redacted = safety.redact_codex(events)
    assert redacted[0]["item"]["result"]["redacted"] is True
    assert redacted[1]["item"]["result"] == "AI"
