from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path("src/rag_enterprise_langgraph/static/app.js")


def _function_source(name: str) -> str:
    script = APP_JS.read_text(encoding="utf-8")
    match = re.search(rf"function {name}\(.*?\n}}\n", script, flags=re.S)
    assert match, name
    return match.group(0)


def test_evidence_cards_never_print_the_raw_locator():
    script = APP_JS.read_text(encoding="utf-8")
    assert "esc(citationPlace(item.locator) ||" in script
    assert "esc(item.locator ||" not in script


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_citation_place_formats_json_and_plain_locators():
    cases = {
        '{"section": "Hotel caps", "heading_level": 2}': "Hotel caps",
        '{"heading": "Leave", "page": 3}': "Leave · page 3",
        "Section 4.3.5": "Section 4.3.5",
        "{not json": "{not json",
        "{'section': 'Hotel caps', 'heading_level': 2}": "Hotel caps",
        '{"sheet": "Rates", "range": "A1:C9"}': "sheet Rates · A1:C9",
        "": "",
    }
    program = _function_source("citationPlace") + (
        f"const cases = {json.dumps(list(cases))};\n"
        "console.log(JSON.stringify(cases.map(citationPlace)));\n"
        'console.log(JSON.stringify([citationPlace({section: "A", row: 0}), citationPlace(null)]));\n'
    )
    output = subprocess.run(
        ["node", "-e", program], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert json.loads(output[0]) == list(cases.values())
    assert json.loads(output[1]) == ["A · row 0", ""]
