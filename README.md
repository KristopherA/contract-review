# contract-review

A [Hermes Agent](https://hermes-agent.nousresearch.com/) skill (agentskills.io
format) that reviews contracts **entirely on your machine** with a local
Ollama model.

> [!WARNING]
> **Not legal advice.** This tool helps you read documents faster. It can miss
> or misread terms, and the model's summaries can be wrong. Always check the
> source document, and talk to a qualified lawyer before you rely on anything
> it produces.

## What it does

1. **Outline**: every real article/clause with its title and cited key facts
   (amounts, percentages, time periods, dates, deadlines, who shall/must/may do
   what), extracted deterministically with no model. The table of contents and
   `(a)`/`(i)`/`1.` list items are skipped. Optional plain-language summaries
   (`--summaries`, off by default) can be written by Hermes. Standard boilerplate is folded away using an editable library
   (`assets/boilerplate.yaml`, fuzzy matched with a threshold).
2. **Diff**: aligns sections between two versions even when they are
   renumbered or moved (title + content similarity), shows a word-level diff,
   and the model writes a one-line plain summary per change.
3. **Evolution**: follows one named section across N versions as a timeline
   with a summary.

Deterministic work (PDF/DOCX/TXT extraction, splitting, alignment, diffing,
boilerplate matching) is done by `scripts/contract_review.py`, which emits JSON
or Markdown. The model only makes the judgment calls. The helpers make no
network calls (a test checks this).

## Setup

### 1. Ollama and a tool-capable model

```sh
# install Ollama from your package manager or https://ollama.com, then:
ollama pull qwen3.5:27b        # or: ollama pull gemma4:31b
```

Give the model a 64k context. Either create a variant with a Modelfile:

```
# Modelfile
FROM qwen3.5:27b
PARAMETER num_ctx 64000
```

```sh
ollama create qwen3.5-64k -f Modelfile
```

or set it for the server with `OLLAMA_CONTEXT_LENGTH=64000 ollama serve`.
Then point Hermes at the local Ollama endpoint (`http://127.0.0.1:11434`) and
that model with `hermes model` / `hermes setup`. Check your Hermes version's
docs for the exact provider option.

### 2. Python dependencies

Python 3.10+. Poppler's `pdftotext` is optional but preferred for PDFs
(`brew install poppler` or `apt install poppler-utils`); `pypdf` is the fallback.

```sh
python3 -m pip install --user -r requirements.txt   # pypdf, rapidfuzz, PyYAML, defusedxml (pinned)
```

### 3. Install the skill

```sh
./install.sh        # copies to ~/.hermes/skills/contract-review/
```

Reinstalling keeps your edited `assets/boilerplate.yaml`. Hermes picks the
skill up on your next message; `/reload-skills` refreshes the slash command.

## Usage

In Hermes:

```
/contract-review outline ~/Contracts/msa-2026.pdf
/contract-review compare ~/Contracts/msa-2025.docx with ~/Contracts/msa-2026.docx
/contract-review how has the Termination clause changed across v1.pdf v2.pdf v3.pdf
```

Helpers directly:

```sh
S=~/.hermes/skills/contract-review/scripts/contract_review.py
python3 $S outline contract.pdf --format md
python3 $S outline contract.pdf --summaries summaries.json --format md   # optional
python3 $S diff old.docx new.docx > changes.json
python3 $S diff old.docx new.docx --summaries summaries.json --format md > diff.md
python3 $S evolve v1.pdf v2.pdf v3.pdf --section "Termination" --format md
python3 $S evolve v1.pdf v2.pdf --section "Article 12"        # or "§12.01", "Appendix A 1.02"
python3 $S evolve v1.pdf v2.pdf --section overtime           # partial, case-insensitive title
```

Reports are Markdown and open in any Markdown viewer.

### Boilerplate library

Edit `assets/boilerplate.yaml`. Each clause needs `id` and `text`; `threshold`
(0-100) is global with optional per-clause overrides. Use `--library` for another
file and `--no-fold` to keep everything. The default threshold is 95, and a
section is never folded if its numbers, negation/exception words or content words
differ from the library text, so "does not constitute" or "except Schedule 3" stays
visible for review. Words are compared in order and only "hereby" is ignored, so even
"a" vs "the" or "or" vs "and" keeps the section in the outline; only case, punctuation
and whitespace differences fold.

### Limits

DOCX parts over 20 MB uncompressed or with a compression ratio over 100, DOCX files
with DOCTYPE/ENTITY declarations, PDFs over 50 MB or 500 pages are refused with a
clean `error:` message (exit 2). Page counts are checked first with pdfinfo and pypdf
(which walks the real page tree); if they disagree, or pdftotext's output has a different
number of pages, the file is refused. If pypdf is not installed this cross-check is
skipped and only pdfinfo's count (from the file's /Count entry) is used, so
long PDFs are refused, never truncated. pdftotext has a 120 s timeout and falls back to
pypdf. DOCX XML is parsed with defusedxml (DTDs forbidden).

## Development

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Tests use only synthetic contracts (fictional parties such as Example Corp)
and generate their PDF and DOCX fixtures at run time.

## Limitations

- No OCR: scanned PDFs need a text layer.
- Page numbers that differ from the PDF page index by more than 6 (long unnumbered front
  matter) are not recognised as page furniture and stay in the text as bare numbers.
- Section splitting expects numbered headings (`1.`, `1.1`, `Section 3`,
  `Article IV`) and upper-case annex headings. Unnumbered, multi-column body
  text or table-heavy layouts split poorly; a letter without a `Re:` line gets a
  derived title.
- After an annex/schedule, the main body resumes only on an `ARTICLE N` heading,
  a new annex heading, or an `N.` that the table of contents lists as a main
  article (and that does not continue the schedule's items). A `1. TITLE`
  document with no TOC keeps everything after its first schedule in that
  schedule. Header/footer removal never drops a heading line; the rules are
  pinned by the layout corpus in `tests/layout_cases.py`.
- Evolve finds a clause by id, number, then title (equal, whole-word substring,
  fuzzy), then follows it by alignment; see Draft 15 rules.
- DOCX extraction reads the main body only (no headers, footers, comments or
  tracked-change markup; deleted revisions may appear as text).
- Alignment is greedy and heuristic; low-score matches should be checked.

## License

MIT. See [LICENSE](LICENSE).

## Draft 11
Body-page header/footer counting, no-TOC numbering-gap resume, dropped repeated/continued
headings, Definition facts, 8-word `who` cap, agreeing word/figure pairs only, quiet pypdf,
and label-stripped boilerplate matching with generic CBA clauses. See
references/helper-output.md, "Draft 11 rules". Tests: `pytest -q` prints the true count.

## Draft 12
Safer boilerplate label stripping, odd/even rule limited to running titles with a partner,
definition plus obligation, "half a day", bare "(n) days", continued LOUs, restated articles
merged without loss, and a stderr warning on the no-TOC gap resume. See
references/helper-output.md, "Draft 12 rules".

## Draft 13 rules

- **Alternating book footers:** if two different edge lines (any text, including sentences, modal verbs, $ or %, but not headings or numbered clause lines) share one slot and alternate by page parity, each on at least 80% of its own parity's body pages and on under half of the other parity's, both are dropped (draft 14: only with at least 4 body pages of each parity; digits are masked first, so "Page 4"/"Page 6" count as one line). A dropped line with a modal verb, $ or % prints a stderr warning. A lone odd-only or even-only line with no partner is still kept.
- **Boilerplate labels:** a clause label is stripped before matching only if it follows the section's own numbering (12.xx in Article 12) and the numbers go up in order. A paragraph such as "30.5 Employees shall…" blocks the fold. In a section with no numeric number (appendix, LOU), the first label sets the numbering and must end in .01 or .1; otherwise no label is stripped (draft 14).
- **Reference numbers:** after subsection, ss., sub-clause, paragraph, para., subparagraph, item, or a dotted clause number (12.01, 12.01(a)), a bracketed figure is a reference, not a duration.
- **Subjectless clause after a definition:** "X means … and shall …" gives an obligation whose subject is the defined term.
- **Restated article:** a repeated clause number in a merged restatement is cited as "N (restated)".
- **Annex ids:** "APPENDIX A-1: SHIFT" is Appendix A-1 with the title SHIFT.

## Draft 14 rules

- **Evolve section lookup:** `--section` is matched in each version on its own, in this order: exact section id (`s4`); clause number (`12`, `§12`, `Article 12`, `12.01`, `§12.01`, `Appendix A 1.02`; a cite inside a section returns that section); title equal (case-insensitive); title substring (`overtime` finds `OVERTIME AND CALL-BACK`; the tightest title wins); fuzzy title (rapidfuzz, score 70+). A renumbered clause is still found by title. If a version has no match, the previous version's section is followed by alignment. When other titles also match, the best is used and the rest are listed on stderr (`warning: ... also close: ...`). If the best candidates tie exactly (e.g. `overtime` for `OVERTIME RATES` and `OVERTIME BANKS`), evolve exits 2 and lists them; use a number or a longer title. (Draft 15 changes this: see below.) Each timeline entry has `matched_by` (`id`, `number`, `title`, `title-substring`, `title-fuzzy`, `aligned`) and, for a cite, `matched_part`.
- **References:** a keyword with its number before a bracket is a reference, not a duration: "Clause 12 (10) days", "in Article 7, (10) days", "Appendix A (2) days".
- **Definitions:** "A day means ... and shall not include holidays" (include, exclude, mean, apply, be deemed ...) stays part of the definition; no obligation is made for the term.

## Draft 15 rules

- **Evolve follows the clause, not the name:** the query is matched directly (id, number, title) only until it is first found. In every later version the clause is followed by alignment from the previous version's section, so a renamed WAGES -> SALARIES is followed even when a lookalike title (STAGES, WAIVERS) exists. A direct match is used only when alignment finds nothing (for example after a removal); if it names a different section than alignment, that is listed on stderr. `matched_by` is `aligned`, `aligned+<how>` when both agree, or the direct method. This replaces the draft 14 note that a number query follows the number.
- **Whole words:** a title substring must start and end on word boundaries: `Termination` does not match DETERMINATION OF SENIORITY, `pay` does not match REPAYMENT, `art` does not match DEPARTURE. Fuzzy matching (rapidfuzz, 70+) is still the last resort.
- **Ties:** a tie in a later version is broken by alignment from the previous version. Only a tie with nothing to follow (the first version that matches) exits 2 with the candidates.
- **Section ids are positional:** `s2` is the second section of that version and shifts after an insertion. An id query prints a stderr warning; prefer a number or a title.
- **Query forms:** at most 200 characters (longer exits 2). `12,01` is read as `12.01`. `12.01(a)` follows §12.01, because sub-items are not sections (noted on stderr). `LOU 3` is Letter of Understanding 3; bare `LOU` (or `Appendix`) picks the only one, or exits 2 listing them. A query with no match in any version prints guidance on stderr.
- **Appendix labels:** in a section with a non-numeric number (appendix, LOU), clause labels are stripped for boilerplate matching only if the first is 1.01 or 1.1 and they go up in order; `30.01` or `2.1` first strips nothing.
- **Report labels:** section titles in Markdown tables are escaped (`|`, `*`, ...).

### Known trade-offs

- With fewer than 4 body pages of each parity, an alternating Pension-style sentence footer is kept (it leaks into the text and can produce an obligation); the 4-page minimum avoids dropping real clauses in short documents.
- Digit masking can pair a real clause that differs only by numbers across odd/even pages (for example "Shift 1 ..." / "Shift 2 ..." lines at a page edge) with a partner line and drop it. When a dropped line has a modal verb, $ or %, the stderr warning fires; check it.
