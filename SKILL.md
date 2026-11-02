---
name: contract-review
description: Outline a contract (parties, dates, term, termination, money, liability, confidentiality, unusual terms) with clause citations, diff two versions with aligned sections and plain one-line summaries, or trace one clause across versions. Use for PDF, DOCX or text contracts. Runs offline; not legal advice.
version: 0.1.0
license: MIT
compatibility: Hermes Agent with the terminal toolset, Python 3.10+, local Ollama model (64k context). Optional poppler pdftotext. No network access needed.
platforms: [macos, linux]
metadata:
  author: KristopherA
  hermes:
    tags: [contracts, legal, diff, documents, offline]
    category: productivity
    requires_toolsets: [terminal]
    config:
      - key: contract_review.library
        description: Path to your boilerplate clause library (YAML)
        default: "~/.hermes/skills/contract-review/assets/boilerplate.yaml"
        prompt: Boilerplate library path
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

1. `python3 $SKILL/scripts/contract_review.py outline FILE [--library PATH]`
   returns JSON: `sections` (each with `cite`, `text`, `topic_hints`, `dates`,
   `amounts`, `durations`) and `boilerplate_folded` (standard clauses removed).
2. Write the report with [templates/outline.md](templates/outline.md). For every
   topic (parties, dates, term/renewal, termination, money/rates,
   liability/indemnity, confidentiality, unusual) give short bullets, each ending
   with its citation, e.g. `(§4 Fees and Payment)`. Hints are leads, not answers:
   read the section text. Write "Not found" rather than guessing.
3. "Unusual" = anything one-sided, uncapped, auto-renewing with long notice,
   unilateral change rights, unusual governing law, or missing a topic you expected.
4. List folded boilerplate at the end in one line each.

## 2. Diff old vs new

1. `python3 $SKILL/scripts/contract_review.py diff OLD NEW > changes.json`
   Each change has `id`, `kinds` (modified, renumbered, moved, retitled, added,
   removed), `old`, `new`, and `word_diff` ops.
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
