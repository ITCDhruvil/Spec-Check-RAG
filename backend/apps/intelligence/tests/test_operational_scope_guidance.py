from apps.intelligence.prompts.templates import (
    build_operational_scope_guidance,
    summary_user_prompt,
)


def test_guidance_stub_returns_empty():
    assert build_operational_scope_guidance({"submission_deadlines": {"items": [{}]}}) == ""


def test_summary_user_prompt_stub_returns_empty():
    assert summary_user_prompt("{}", "example.pdf") == ""
