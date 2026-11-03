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
- Evolve matches a clause by number or by a close title; a short or different
  name (e.g. a single word for a longer heading) may report it as absent.
- DOCX extraction reads the main body only (no headers, footers, comments or
  tracked-change markup; deleted revisions may appear as text).
- Alignment is greedy and heuristic; low-score matches should be checked.

## License

MIT. See [LICENSE](LICENSE).
