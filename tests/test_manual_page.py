from __future__ import annotations

import hashlib

from scripts.generate_manual_page import build_page, render_markdown, write_page


def test_manual_renderer_escapes_html_and_renders_tables():
    source = "# Manual\n\n| Rule | Value |\n|---|---|\n| Limit | <script> |\n"
    rendered = render_markdown(source)
    assert "<h1>Manual</h1>" in rendered
    assert "<table>" in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered


def test_manual_page_records_exact_source_hash(tmp_path):
    source = tmp_path / "manual.md"
    output = tmp_path / "index.html"
    body = "# Northwind Manual\n\nPublic synthetic demonstration content.\n"
    source.write_text(body, encoding="utf-8")
    digest = write_page(source, output)
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
    page = output.read_text(encoding="utf-8")
    assert digest == expected
    assert expected in page
    assert "no real company" in page.lower()
    write_page(source, output, check=True)


def test_page_has_no_unverified_page_count():
    page = build_page("# Manual", source_sha256="a" * 64)
    assert "pages" not in page.lower()
