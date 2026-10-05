from __future__ import annotations

import hashlib
import json

import pytest

from rag_enterprise_langgraph.eval_runner import EvalSetError, _external_prompt_metadata


def _write(root, name: str, text: str) -> str:
    (root / name).write_text(text + "\n", encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture()
def starter(tmp_path):
    root = tmp_path / "backend/app/llm/prompt_assets"
    root.mkdir(parents=True)
    current = _write(root, "answer-v1.1.0.txt", "current")
    candidate = _write(root, "answer-v1.2.2.txt", "candidate")
    pinned = _write(root, "answer-v1.2.3.txt", "pinned")
    registry = {
        "schema_version": "1.0",
        "prompts": {
            "starter_answer": {"version": "1.1.0", "file": "answer-v1.1.0.txt", "sha256": current}
        },
        "candidates": {
            "starter_answer": {
                "version": "1.2.2",
                "file": "answer-v1.2.2.txt",
                "sha256": candidate,
            }
        },
        "history": {"starter_answer": {"1.2.3": {"file": "answer-v1.2.3.txt", "sha256": pinned}}},
    }
    (root / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("env", "version"),
    [
        ({}, "1.2.2"),  # STARTER's default: candidate on
        ({"ANSWER_PROMPT_CANDIDATE": "true"}, "1.2.2"),
        ({"ANSWER_PROMPT_CANDIDATE": "false"}, "1.1.0"),
        ({"ANSWER_PROMPT_VERSION": "1.2.3"}, "1.2.3"),
        ({"ANSWER_PROMPT_VERSION": "1.2.3", "ANSWER_PROMPT_CANDIDATE": "false"}, "1.2.3"),
    ],
)
def test_reports_the_answer_prompt_starter_actually_uses(starter, monkeypatch, env, version):
    monkeypatch.delenv("ANSWER_PROMPT_CANDIDATE", raising=False)
    monkeypatch.delenv("ANSWER_PROMPT_VERSION", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert _external_prompt_metadata(starter)["starter_answer"]["version"] == version


def test_unknown_pinned_version_is_an_error(starter, monkeypatch):
    monkeypatch.setenv("ANSWER_PROMPT_VERSION", "9.9.9")
    with pytest.raises(EvalSetError, match=r"9\.9\.9"):
        _external_prompt_metadata(starter)
