#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GPTBots knowledge-base file quality-check script (offline, zero network, pure standard library).

After curating a source document into an import-ready file, run this script on every emitted
file; on a non-zero exit code, read the errors, fix, and rerun, delivering/prompting import
only after it passes. The rules mirror the platform's three storage formats and the curation
disciplines in references/organize-knowledge-base.md:
  - Q&A   : a CSV whose header is exactly `question,answer`; both cells non-empty; one Q -> one A.
  - Table : a CSV/TSV with a header row; every data row has the same column count; image cells
            are embedded Markdown `![](http...)`, not a bare URL.
  - Doc   : a Markdown file; images are `![](http...)` (no bare image URLs / "(image here)"
            placeholders); heading structure present.

Authoritative sources in oversea-ailab:
  - common/enums/BotDataSegmentType.java       (SPREADSHEET / TEXT / QA / STRUCTURED / CSV_TEMPLATE)
  - common/enums/BotDataPurposeType.java        (QA_FILE / FILE_2_QA / SPREADSHEET / TEXT / ...)
  - bot/bean/entity/QuestionAnswer.java         (fields: question, answer)
  - bot/bean/entity/BotDataSplitRule.java        (headerType R1/R2/R3 | C1/C2/C3, token, delimiter)
When the platform changes, re-sync against these and bump the skill version.

Usage:
  python3 validate_knowledge_files.py <file> [--type qa|table|doc|auto] [--json]
Type detection (when --type auto, the default):
  - *.md / *.markdown          -> doc
  - *.csv / *.tsv with a header containing both `question` and `answer` (case-insensitive) -> qa
  - any other *.csv / *.tsv    -> table
Exit codes: 0 = pass (no error); 1 = has error; 2 = usage/read error.
"""
import argparse
import csv
import io
import os
import re
import sys

# A real, embeddable image: Markdown ![alt](http(s)://...) with a non-blank URL.
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*(?P<url>[^)\s]+)\s*\)")
# A bare URL that points at an image file (should have been wrapped as ![](...)).
BARE_IMAGE_URL_RE = re.compile(r"(?<!\()\bhttps?://[^\s)]+\.(?:png|jpe?g|gif|webp|bmp|svg)\b", re.I)
# Placeholder left behind instead of a real image.
IMAGE_PLACEHOLDER_RE = re.compile(r"(图片地址|图片如下|见图|\(?\s*(image|图片)\s*(here|here\.)?\s*\)?)", re.I)
# The internal Q/A join token the backend uses; must not appear inside a field.
QA_JOIN_TOKEN = "---***---"


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []

    def err(self, code, path, message, fix=""):
        self.errors.append({"code": code, "path": path, "message": message, "fix": fix})

    def warn(self, code, path, message, fix=""):
        self.warnings.append({"code": code, "path": path, "message": message, "fix": fix})

    def note(self, message):
        self.info.append(message)

    @property
    def ok(self):
        return len(self.errors) == 0


def _read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    # utf-8-sig strips a BOM if Excel added one.
    return raw.decode("utf-8-sig")


def _sniff_csv(text):
    """Return (rows, dialect_delimiter). Falls back to comma on sniff failure."""
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    # Drop trailing fully-empty rows (Excel often appends them).
    while rows and all((c or "").strip() == "" for c in rows[-1]):
        rows.pop()
    return rows, delim


def detect_type(path, text):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".md", ".markdown"):
        return "doc"
    if ext in (".csv", ".tsv"):
        rows, _ = _sniff_csv(text)
        header = [(c or "").strip().lower() for c in (rows[0] if rows else [])]
        if "question" in header and "answer" in header:
            return "qa"
        return "table"
    # Unknown extension: guess from content.
    if "question" in text[:200].lower() and "answer" in text[:200].lower():
        return "qa"
    return "doc"


def check_qa(text, rep):
    rows, _ = _sniff_csv(text)
    if not rows:
        rep.err("QA_EMPTY", "$", "The Q&A file is empty", "Add a `question,answer` header and at least one pair")
        return
    header = [(c or "").strip().lower() for c in rows[0]]
    if "question" not in header or "answer" not in header:
        rep.err("QA_HEADER", "row 1",
                f"Q&A header must contain `question` and `answer` (found: {rows[0]})",
                "Make the first row exactly: question,answer")
        return
    qi, ai = header.index("question"), header.index("answer")
    pairs = 0
    for n, row in enumerate(rows[1:], start=2):
        q = row[qi].strip() if qi < len(row) else ""
        a = row[ai].strip() if ai < len(row) else ""
        if q == "" and a == "":
            continue  # skip blank line
        if q == "":
            rep.err("QA_EMPTY_Q", f"row {n}", "question is empty", "Every pair needs a non-empty question")
        if a == "":
            rep.err("QA_EMPTY_A", f"row {n}", "answer is empty", "Every pair needs a non-empty answer")
        if QA_JOIN_TOKEN in q or QA_JOIN_TOKEN in a:
            rep.err("QA_JOIN_TOKEN", f"row {n}",
                    f"a field contains the reserved token {QA_JOIN_TOKEN!r}",
                    "Remove it — the backend uses it internally to join Q and A")
        if q and a:
            pairs += 1
    if pairs == 0:
        rep.err("QA_NO_PAIRS", "$", "No complete question/answer pairs found")
    else:
        rep.note(f"{pairs} Q&A pair(s)")


def check_table(text, rep):
    rows, delim = _sniff_csv(text)
    if not rows:
        rep.err("TBL_EMPTY", "$", "The table file is empty", "Add a header row and at least one data row")
        return
    header = rows[0]
    if all((c or "").strip() == "" for c in header):
        rep.err("TBL_HEADER", "row 1", "The header row (row 1) is blank",
                "Put one column name per attribute in row 1 (import as headerType R1)")
    ncols = len(header)
    if len(rows) < 2:
        rep.warn("TBL_NO_DATA", "$", "The table has a header but no data rows")
    data_rows = 0
    for n, row in enumerate(rows[1:], start=2):
        if all((c or "").strip() == "" for c in row):
            continue
        data_rows += 1
        if len(row) != ncols:
            rep.err("TBL_RAGGED", f"row {n}",
                    f"row has {len(row)} columns but the header has {ncols}",
                    "Give every row the same number of columns as the header (mind unquoted delimiters)")
        for ci, cell in enumerate(row):
            cell = (cell or "").strip()
            if BARE_IMAGE_URL_RE.search(cell) and not MD_IMAGE_RE.search(cell):
                rep.warn("TBL_BARE_IMG", f"row {n}, col {ci + 1}",
                         "image cell is a bare URL",
                         "Wrap it as ![](URL) so the image is embedded and tied to this row")
    rep.note(f"{ncols} column(s), {data_rows} data row(s), delimiter={delim!r}")


def check_doc(text, rep):
    if text.strip() == "":
        rep.err("DOC_EMPTY", "$", "The document is empty")
        return
    # Bare image URLs that should be Markdown images.
    for m in BARE_IMAGE_URL_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        rep.warn("DOC_BARE_IMG", f"line {line}",
                 f"bare image URL: {m.group(0)}",
                 "Wrap it as ![](URL) so the image survives import")
    # Placeholder text instead of a real image.
    for m in IMAGE_PLACEHOLDER_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        rep.warn("DOC_IMG_PLACEHOLDER", f"line {line}",
                 f"possible image placeholder: {m.group(0).strip()!r}",
                 "Replace with the real ![](URL), or remove if there is no image")
    # Markdown images with a blank/relative (non-http) URL.
    for m in MD_IMAGE_RE.finditer(text):
        url = m.group("url")
        if not url.lower().startswith(("http://", "https://")):
            line = text.count("\n", 0, m.start()) + 1
            rep.warn("DOC_IMG_LOCAL", f"line {line}",
                     f"image URL is not a public http(s) URL: {url}",
                     "Use the cloud URL the platform expects, or upload the image first")
    if not re.search(r"^#{1,6}\s+\S", text, re.M):
        rep.warn("DOC_NO_HEADINGS", "$",
                 "no Markdown headings found",
                 "Add #/##/### headings so chunking has sensible boundaries (skip if the doc is genuinely flat)")
    rep.note(f"{len(text.splitlines())} line(s)")


CHECKERS = {"qa": check_qa, "table": check_table, "doc": check_doc}


def main(argv):
    parser = argparse.ArgumentParser(description="GPTBots knowledge-base file quality check")
    parser.add_argument("file", help="path to the .md / .csv knowledge file")
    parser.add_argument("--type", choices=["qa", "table", "doc", "auto"], default="auto",
                        help="storage format to validate as (default: auto-detect)")
    parser.add_argument("--json", action="store_true", help="output the result as JSON")
    args = parser.parse_args(argv)

    try:
        text = _read_text(args.file)
    except OSError as e:
        print(f"Unable to read file: {e}", file=sys.stderr)
        return 2

    ftype = detect_type(args.file, text) if args.type == "auto" else args.type
    rep = Report()
    CHECKERS[ftype](text, rep)

    result = {"ok": rep.ok, "type": ftype, "errors": rep.errors,
              "warnings": rep.warnings, "info": rep.info}
    _emit(result, args.json)
    return 0 if rep.ok else 1


def _emit(result, as_json):
    import json
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    head = f"[{result['type']}]"
    if result["ok"]:
        extra = f" ({len(result['warnings'])} warning(s))" if result["warnings"] else ""
        print(f"✅ {head} Quality check passed{extra}")
    else:
        print(f"❌ {head} Quality check failed: {len(result['errors'])} error(s), "
              f"{len(result['warnings'])} warning(s)")
    for e in result["errors"]:
        print(f"  [ERROR {e['code']}] {e['path']}: {e['message']}"
              + (f" → {e['fix']}" if e['fix'] else ""))
    for w in result["warnings"]:
        print(f"  [WARN  {w['code']}] {w['path']}: {w['message']}"
              + (f" → {w['fix']}" if w['fix'] else ""))
    for note in result["info"]:
        print(f"  [info] {note}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
