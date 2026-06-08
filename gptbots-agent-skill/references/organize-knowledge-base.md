# Organize / curate knowledge-base source documents

Turn a user's **raw, messy source material** (PDF / Word / Excel / web export / scattered
FAQ / notes) into **clean, import-ready files** for a GPTBots Agent's knowledge base, and
advise on the platform-side settings (chunking, metadata, retrieval) that make those files
recall well. Use this when the user wants to *prepare*, *clean up*, *restructure*, *de-dup*,
or *optimize* knowledge for upload — **not** when they want to edit a `.bot`/`.flow` config.

The GPTBots backend parses every uploaded document into one of **three storage formats**.
Your job is to pick the right format per piece of content and emit a file that imports
cleanly into it. (Authoritative source: `oversea-ailab` enum `BotDataSegmentType`
= `SPREADSHEET / TEXT / QA / STRUCTURED / CSV_TEMPLATE`; import purpose `BotDataPurposeType`
= `QA_FILE / FILE_2_QA / SPREADSHEET / TEXT / QA_TEXT / ...`.)

## The three storage formats (authoritative)

| Format | `SegmentType` | Source files | How it is chunked | Emit as |
|---|---|---|---|---|
| **Document** (text) | `TEXT` | `.doc .docx .pdf .md .txt`, URL, pasted text | by **token** or by **delimiter** | a `.md` file |
| **Table** (spreadsheet) | `SPREADSHEET` | `.xls .xlsx .csv` | **header + one chunk per row** (stored as row-wise JSON, header retained) | a `.csv` (UTF-8) or `.xlsx` |
| **Q&A** | `QA` | `.csv` (`QA_FILE`), or doc→QA (`FILE_2_QA`) | **one chunk per Q&A pair** (automatic) | a `.csv` with header `question,answer` |

### Document (Markdown / `TEXT`)
The backend converts the source to Markdown, preserving **headings & hierarchy, ordered/
unordered lists, tables, code blocks, and images**. Images found in a PDF/Word are uploaded
to cloud storage and embedded as `![](https://…)`. So when you hand-curate document content:
- Keep the real heading structure (`#`, `##`, `###`) — it drives sensible chunk boundaries.
- Keep lists, tables, and code blocks as Markdown; do not flatten them into prose.
- Every image must be a Markdown image with a **real URL**: `![alt](https://…)`. Never leave a
  bare `图片地址: https://…` line or a placeholder like "(there was an image here)".

### Table (`SPREADSHEET`)
The platform slices a table into **one chunk per data row**, keeping the header so each row
chunk reads as "header → value". The user picks which line(s) are the header in the import
dialog via `headerType`: **rows** `R1` / `R2` / `R3` (first 1/2/3 rows are the header, default
`R1`) or **columns** `C1` / `C2` / `C3`. There are **no fixed column names** — the header is
whatever the user's first row says. So your job is to deliver a *clean* sheet:
- **First row = the header**, one column per attribute. Keep it to `R1` unless the data
  genuinely has a 2–3 row header.
- **One record per row.** Process **every row precisely** — do not sample or summarize.
- **Image column = embedded mode.** If a record has an image, keep it in its own column and
  put `![](https://…)` **in that row's cell** (not a bare URL). The image belongs to that row
  and is part of that row's answer — it must be preserved, never dropped.
- Prefer a table over Q&A when the data is attribute/record-shaped — GPTBots parses tables
  natively, so you do **not** need to explode every row into a Q&A pair.

### Q&A (`QA`)
Each pair becomes one chunk. Deliver a UTF-8 CSV whose header is exactly **`question,answer`**
(these column names are fixed in the backend; they are not localized). Both fields are
**required and non-empty**; the structure is strictly **one question → one answer** (no
multi-answer). Images go **inside the answer** as `![](https://…)` or a URL.

## Choosing a format

| The content is… | Use | Why |
|---|---|---|
| Prose, manuals, articles, specs with structure/headings/images | **Document** | Preserves structure; chunk by section |
| Records/rows with the same fields (catalogs, price lists, specs, inventories) | **Table** | One chunk per row; precise field-level recall |
| Distinct question→answer pairs (FAQ, support macros, policy Q&A) | **Q&A** | One chunk per pair; highest-precision FAQ recall |

Don't force everything into Q&A. Tables are a first-class type; long-form knowledge belongs in
a Document. Split one messy source into **multiple files of different formats** when it mixes
shapes (e.g. a doc that contains both narrative and a spec table → one `.md` + one `.csv`).

## Curation workflow

1. **Inspect & classify.** Read the source, identify which parts are prose vs. records vs.
   Q&A pairs, and split accordingly.
2. **Transform per format** using the rules above.
3. **Apply the curation disciplines (below).**
4. **Validate.** Run `python3 scripts/validate_knowledge_files.py <file> --type qa|table|doc`
   on every emitted file — pass `--type` explicitly (you know the intended format; auto-detect
   would classify a Q&A CSV with a wrong header as a plain table and miss the error). Fix
   anything it reports before delivering.
5. **Deliver** the import-ready files plus a short import guide (see Delivery).

### Curation disciplines (do not skip)
- **Process every row/pair precisely.** No sampling, no "…and so on", no summarizing rows away.
- **Merge exact duplicates.** Collapse byte-identical rows/pairs into one. Log how many you merged.
- **Preserve the original wording.** Clean structure and formatting, but **do not invent,
  expand, paraphrase, or add sections** that were not in the source. "Curate" ≠ "rewrite".
- **Conflicting info → a separate table; never silently pick a winner.** When two rows
  disagree on the same key (e.g. the same model at two different prices), keep **both** in a
  dedicated `*-conflicts.csv` (with whatever distinguishing context exists) and flag it for the
  user to resolve. Do not delete one value or quietly choose — that destroys information.
- **Preserve images.** Every image in the source must survive: `![](url)` in the document, in
  the table's image cell, or inside the Q&A answer.

## Platform-side settings (advise the user)

### Chunking
- **Token mode**: one chunk per N tokens (range `1`–`1000000`). Good default for prose.
- **Delimiter mode**: split on `\n`, `\n\n`, or `\n\n\n\n` — use when the document already has
  clean paragraph/section breaks.
- **Table**: header + one row per chunk (set `headerType` = `R1`/`R2`/`R3`).
- **Q&A**: automatic, one pair per chunk (no setting).
- Chunk too **large** pulls in unrelated text (noise); too **small** loses context. Start with
  the default, then verify with **Hit Testing** and adjust.

### Metadata (for filtered retrieval)
Beyond the auto system fields (knowledge base, document name, uploader, upload/update time,
source, storage type, file format), define **custom metadata fields** (up to **50**) to filter
recall to a smaller, more relevant set:
- Types: **STRING / NUMBER / DATETIME / LIST**.
- Field name: lowercase, starts with a letter, `[a-z0-9_]`, ≤ **32 chars**, **immutable after
  creation** (the display label is editable). Scope is **global** or **per-knowledge-base**.
- Tag documents with source, product line, version, effective date, status, etc., so the Agent
  can pre-filter before vector/graph recall.

### Retrieval tuning & hit testing
- **Mode**: **Hybrid (recommended)** balances semantics + exact match; Semantic for paraphrase-
  heavy queries; Keyword for codes/IDs/exact terms.
- **Similarity threshold** ↑ = more precise but may miss; ↓ = broader but noisier.
- **TopK** trades precision vs. coverage; **Rerank** re-orders recalled chunks; **Query
  enhancement** rewrites/expands the user question to widen recall.
- **Knowledge graph** is built automatically (entities + relations, surfaced as a `GRAPH_TRIPLE`
  virtual chunk). Enable graph recall when knowledge is entity/relationship-rich and questions
  need multi-hop or cross-document reasoning; it adds little for sparse, single-fact lookups.
- There is no universal "best" setting — start at defaults, run **Hit Testing** with realistic
  user questions, inspect the recalled chunks, then adjust one knob at a time.

## Delivery
1. Write the import-ready files to the current working directory and return their paths:
   - Document → `<name>.md`
   - Table → `<name>.csv` (UTF-8) or `<name>.xlsx`; conflicts → `<name>-conflicts.csv`
   - Q&A → `<name>-qa.csv` with header `question,answer`
2. Run the validator on each and report it passed.
3. Tell the user how to import: GPTBots developer space → the Agent → **Knowledge base → Add**,
   then choose the matching type (Document / Table / Q&A); for a Table, select the header row
   (`R1`/`R2`/`R3`) in the dialog. Then advise chunking / metadata / hit-testing per above.
4. Surface any judgement calls (conflicts, dropped duplicates) for the user to confirm.

## Common mistakes
| Mistake | Fix |
|---|---|
| Rendering record/table data as a Markdown table for a Document import | Emit a clean `.csv`/`.xlsx` and use the **Table** type (one chunk per row) |
| Forcing every row into a Q&A pair | Use a Table when the data is record-shaped |
| Bare image URL in a cell or doc (`图片地址: http…`) | Wrap as `![](http…)` so the image is preserved and tied to its row/section |
| Silently choosing one value when rows conflict | Keep both in a `*-conflicts.csv` and flag for the user |
| Rewriting / summarizing / adding content not in the source | Preserve original wording; only restructure |
| Q&A CSV with empty question or answer, or wrong header | Header must be exactly `question,answer`; both cells non-empty |
| Putting the literal token `---***---` inside a Q&A field | Avoid it — the backend uses it internally to join Q and A |
| One giant chunk / over-tiny chunks | Calibrate chunk size with Hit Testing |
