---
name: contract-review
description: Outline a contract (parties, dates, term, termination, money, liability, confidentiality, unusual terms) with clause citations, diff two versions with aligned sections and plain one-line summaries, or trace one clause across versions. Use for PDF, DOCX or text contracts. Runs offline; not legal advice.
license: MIT
compatibility: Hermes Agent with the terminal toolset on macOS or Linux, Python 3.10+, local Ollama model (64k context). Optional poppler pdftotext. No network access needed.
metadata:
  version: "0.1.0"
  author: KristopherA
  hermes-tags: "contracts, legal, diff, documents, offline"
  hermes-category: productivity
  hermes-platforms: "macos, linux"
  hermes-requires-toolsets: terminal
  library-default: "assets/boilerplate.yaml (override with --library PATH)"
allowed-tools: terminal
---

# Contract Review

Use when the user asks to outline, summarise, compare, diff or trace clauses in a
contract. The helper script does all deterministic work (extraction, section
splitting, alignment, word diff, boilerplate folding). You only do judgment:
classify, summarise, flag unusual terms. Never invent clause numbers; cite only
the `cite`/`number` values the helper returns.

Helper (run with the terminal tool; `$SKILL` is this skill's directory, normally
`~/.hermes/skills/contract-review`):

```
python3 $SKILL/scripts/contract_review.py <command> ...
```

## 1. Outline a contract

1. `python3 $SKILL/scripts/contract_review.py outline FILE --format md [--library PATH]`
   prints one heading per real article/clause (`ARTICLE 12`, `12`, `12.01`) with its
   title and deterministic key facts: amounts, percentages, time periods, dates,
   deadlines ("within 30 days") and obligation/right/prohibition sentences, each
   cited (`§12.01`). The table of contents, page footers, and `(a)`, `(i)`, `1.` list
   items are not sections. Standard boilerplate is folded and listed at the end.
   `--format json` gives `sections[].key_facts` for your own use.
2. By default, give the user that outline as is. Do not add a model summary unless
   they ask for one ("summarize", "plain English").
3. Optional plain-language summaries: read each section's `text` from the JSON,
   write one or two sentences per section id using only that text, and save
   `{"s3": "...", ...}` to `summaries.json`. Then rerun with
   `--summaries summaries.json --format md`. Lay it out with
   [templates/outline.md](templates/outline.md). Never add a fact that is not in the
   section's text. Keep the cited key facts under each summary.
4. Flag anything unusual you notice (one-sided, uncapped, unilateral change rights,
   long notice periods) under "Unusual", with citations. Write "Not found" rather
   than guessing.

## 2. Diff old vs new

1. `python3 $SKILL/scripts/contract_review.py diff OLD NEW > changes.json`
   Each change has `id`, `kinds` (modified, renumbered, moved, retitled, added,
   removed, split, merged), `old`, `new`, `score`, `low_confidence` and `word_diff` ops.
   If `low_confidence` is true (score under 65), say in its summary that the
   pairing is uncertain and may be two different clauses; never present it as a
   plain edit.
2. Write one plain-English line per change id into `summaries.json`
   (`{"c1": "...", ...}`). State what changed and its practical effect; do not
   paraphrase unchanged text. Renumber/move-only changes: say so in a few words.
3. `python3 $SKILL/scripts/contract_review.py diff OLD NEW --summaries summaries.json --format md > diff-report.md`
4. Give the user the report path plus the 3 most significant changes.

## 3. Evolution of one section across versions

1. `python3 $SKILL/scripts/contract_review.py evolve V1 V2 V3 ... --section "Termination"`
   (name or number such as `§7`; list files oldest first).
2. Write a 2-4 sentence overall summary to `summary.txt` and optional per-version
   notes to `notes.json` (`{"v2.pdf": "..."}`).
3. Re-run with `--summary-file summary.txt --notes notes.json --format md > evolution.md`.

## Rules

- Everything stays local. Do not call web tools or upload documents.
- Put "Not legal advice" at the top of every report (the helper does this for
  diff and evolution reports; keep it in outlines).
- Large contracts: work from the helper JSON section by section rather than
  loading the whole text; the model context is 64k tokens.
- Details of the JSON fields: [references/helper-output.md](references/helper-output.md).

## Pitfalls

- Scanned PDFs have no text layer; the helper exits with an error. Ask for a text
  PDF or DOCX; OCR is out of scope.
- If headings are not numbered (`1.`, `1.1`, `Section 3`, `Article IV`), the
  document comes back as one Preamble section. Tell the user the split failed.
- A pair matched with a low `score` (under ~70) may be a wrong alignment; check
  the text before summarising it as a modification.
- Boilerplate folding hides near-identical text: if a folded clause matters to
  the user's question, re-run with `--no-fold`.

## Verification

- Every bullet in an outline has a citation that exists in the helper output.
- Every change id in `changes.json` has exactly one summary line.
- The Markdown report opens and shows the "Not legal advice" note.
