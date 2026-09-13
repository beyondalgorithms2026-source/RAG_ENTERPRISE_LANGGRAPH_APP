"""Render the canonical STARTER Operations Manual into the APP Pages tree."""

from __future__ import annotations

import argparse
import hashlib
import html
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = (
    REPO.parent
    / "RAG_ENTERPRISE_STARTER/corpus/source_documents/northwind-operations-manual-v3.2.md"
)
DEFAULT_OUTPUT = REPO / "docs/manual/index.html"


def _inline(value: str) -> str:
    escaped = html.escape(value.strip())
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def render_markdown(source: str) -> str:
    lines = source.splitlines()
    output: list[str] = []
    index = 0
    list_kind: str | None = None

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            output.append(f"</{list_kind}>")
            list_kind = None

    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("|") and index + 1 < len(lines):
            separator = lines[index + 1].strip()
            if separator.startswith("|") and re.fullmatch(r"[|:\- ]+", separator):
                close_list()
                headers = [_inline(cell) for cell in line.strip("|").split("|")]
                output.append('<div class="table-scroll"><table><thead><tr>')
                output.extend(f"<th>{cell}</th>" for cell in headers)
                output.append("</tr></thead><tbody>")
                index += 2
                while index < len(lines) and lines[index].strip().startswith("|"):
                    cells = [_inline(cell) for cell in lines[index].strip().strip("|").split("|")]
                    output.append("<tr>")
                    output.extend(f"<td>{cell}</td>" for cell in cells)
                    output.append("</tr>")
                    index += 1
                output.append("</tbody></table></div>")
                continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            output.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif match := re.match(r"^\d+\.\s+(.+)$", line):
            if list_kind != "ol":
                close_list()
                list_kind = "ol"
                output.append("<ol>")
            output.append(f"<li>{_inline(match.group(1))}</li>")
        elif match := re.match(r"^[-*]\s+(.+)$", line):
            if list_kind != "ul":
                close_list()
                list_kind = "ul"
                output.append("<ul>")
            output.append(f"<li>{_inline(match.group(1))}</li>")
        elif not line:
            close_list()
        else:
            close_list()
            output.append(f"<p>{_inline(line)}</p>")
        index += 1
    close_list()
    return "\n".join(output)


def build_page(source: str, *, source_sha256: str) -> str:
    article = render_markdown(source)
    return f"""<!-- GENERATED FILE. Source: STARTER/corpus/source_documents/northwind-operations-manual-v3.2.md -->
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Northwind Operations Manual v3.2 — Synthetic Demo</title>
<style>
:root{{--bg:#f6f7fb;--card:#fff;--ink:#14161f;--muted:#586373;--line:#d9dde8;--accent:#0e11d8}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 Inter,system-ui,sans-serif}}
main{{max-width:76rem;margin:auto;padding:2rem 1rem 5rem}}.notice{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1rem;margin-bottom:2rem}}
h1{{font-size:2.4rem}}h2{{margin-top:2.5rem;border-top:1px solid var(--line);padding-top:1rem}}h3{{margin-top:2rem}}p,li{{max-width:78ch}}
.table-scroll{{overflow:auto;margin:1rem 0}}table{{border-collapse:collapse;width:100%;background:var(--card)}}th,td{{border:1px solid var(--line);padding:.55rem;text-align:left;vertical-align:top}}th{{background:#eceef5}}code{{overflow-wrap:anywhere}}a{{color:var(--accent)}}
</style></head><body><main>
<div class="notice"><strong>Public synthetic demonstration content.</strong> This fictional manual contains no real company, employee, customer, or private data. Effective 1 September 2026. Canonical-source SHA-256: <code>{html.escape(source_sha256)}</code>. <a href="../evaluation/">View approved evaluation evidence</a>.</div>
{article}
</main></body></html>
"""


def write_page(source_path: Path, output_path: Path, *, check: bool = False) -> str:
    source_bytes = source_path.read_bytes()
    source = source_bytes.decode("utf-8")
    digest = hashlib.sha256(source_bytes).hexdigest()
    rendered = build_page(source, source_sha256=digest)
    if check:
        if not output_path.exists() or output_path.read_text(encoding="utf-8") != rendered:
            raise SystemExit("rendered Operations Manual page is stale")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    digest = write_page(args.source.resolve(), args.output.resolve(), check=args.check)
    print(f"Operations Manual page SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
