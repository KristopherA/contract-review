# Helper output reference

`--pdf-backend auto|pdftotext|pypdf` (global, before the subcommand) picks the PDF extractor.

## Section object
| field | meaning |
|---|---|
| id | stable id within one document (`s0` = preamble) |
| number | clause number as written (`4`, `5.1`, `IV`), empty for preamble |
| title | heading text, may be empty for long numbered sub-clauses |
| level | 1 for `4`, 2 for `4.1`, ... |
| text | clause body, paragraphs joined by blank lines |
| order | position in the document |

## outline
`sections[]` = section + `cite`, `clauses[]` (untitled sub-clause numbers merged in) and
`key_facts` = `{amounts, percentages, durations, dates: [{value, cite}], deadlines:
[{text, cite}], obligations: [{kind: obligation|prohibition|right, who, text, cite}]}`.
Facts are regex-based, no model. `--summaries FILE` (JSON `{section id: text}`) adds a
`**Summary:**` line per section in Markdown; off by default.
Sections: only `ARTICLE/SECTION/CLAUSE N`, `N` and `N.NN` headings count; TOC entries
(dot leaders, page numbers, a CONTENTS block), page footers and `(a)`/`(i)`/`1.` list
items stay out. A clause number must belong to the current article; an untitled
`N.NN` clause is merged into its article as a cited part.
`boilerplate_folded[]` = `{section, id, clause, score}`. Threshold: library `threshold`
(default 95) or `--threshold`; per-clause `threshold` overrides. A section folds only
if, in addition, its numbers/amounts, its negation/exception words (not, no, never,
except, unless, notwithstanding, shall not, provided that, subject to, ...) and its
content words all match the library clause exactly, in order (only "hereby" is ignored;
"a" -> "the" does not fold). Anything else stays in the outline.

## diff
Array of changes `{id, kinds[], old, new, score, word_diff[]}`. `word_diff` ops are
`{op: equal|delete|insert, text}`. Alignment score = 0.35 × title similarity +
0.65 × content similarity (0-100); pairs below `--match-threshold` (default 55) are
reported as removed + added. `moved` means the relative order changed.
A pair with a rewritten title still matches when content similarity alone is ≥ 65.
`split` (with `split_into[]`) = one old section became this one plus neighbours;
`merged` (with `merged_from[]`) = several old sections became this one. Accepted only
when the combined text is ≥ 80 similar and ≥ 10 points better than the single pair;
`word_diff` then runs over the concatenated text. The absorbed sections are not
reported separately, so they lose their `added`/`removed` label; they appear only
inside `split_into[]`/`merged_from[]` of the section that absorbed them.
`low_confidence: true` marks pairs scoring under 65 (e.g. "Governing Law" paired with
"Jurisdiction"); the Markdown report marks them with ⚠.

## Limits
Input files: DOCX `word/document.xml` ≤ 20 MB uncompressed and compression ratio ≤ 100
(read in bounded chunks; DOCTYPE/ENTITY rejected, then parsed with defusedxml); PDF ≤ 50 MB and ≤ 500 pages (counted up front with pdfinfo and pypdf; disagreement, or pdftotext returning a
different number of form-feed pages, is an error. Without pypdf only pdfinfo is used,
so longer files are refused rather than truncated);
pdftotext timeout 120 s (then falls back to pypdf in `auto`). Errors print
`error: ...` and exit 2.

## evolve
`{query, timeline[]}`; each entry `{version, index, present, status, section?,
renumbered_from?, word_diff?}`. Status: baseline, first-seen, changed, unchanged,
removed, reappeared, absent. The section is followed by alignment from the
previous version, falling back to a title/number search.
