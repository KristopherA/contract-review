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
Facts are regex-based, no model. Text is split into sentences first and the regexes run
per sentence; a sentence over 2000 chars is scanned in 2000-char windows overlapping by
200, so matching stays linear, and each fact is reported once. "Nothing shall
prevent…" saving clauses are not listed as obligations. A sentence with `shall not / must not / may not / will not / cannot` is a
prohibition, as is `No X / Nothing / Neither … shall` ("No employee shall be
disciplined"). `--summaries FILE` (JSON `{section id: string}`, max 1 MB) adds a
`**Summary:**` line per section in Markdown; off by default. Values are collapsed to
one line, capped at 2000 chars and Markdown-escaped (including `&`; URLs and emails
become code spans, never links); too-deep JSON exits 2; unknown ids go to stderr as
warnings; any other shape exits 2. `diff --summaries` and `evolve --notes` follow the same rules; `evolve --summary-file` is escaped the same way.
Sections: only `ARTICLE/SECTION/CLAUSE/PART N`, `N` and `N.NN` headings count, plus
annexes (`LETTER OF UNDERSTANDING`, `APPENDIX A`, `SCHEDULE 1`, memorandum, addendum,
annex) which start their own top-level block; an untitled annex takes its title from a
`Re:` line. Clause numbers inside an annex are scoped to it (`Appendix A 1.01`, cited
`Appendix A, §1.01`), so a repeated `1.01` is not a duplicate; a `1. TITLE` line inside
an annex is a clause of that annex (`Schedule C 1`), never a document article. TOC entries (dot
leaders, trailing page numbers, a CONTENTS/INDEX block) and `(a)`/`(i)`/`1.` list
items stay out. Page furniture is dropped: `- N -` and `Page N of M` lines; bare
numbers at the top/bottom of pages that equal the page index plus a small offset (≤6)
on 3+ pages (explicit forms count toward the run); and running headers/footers. A
header/footer is a line identical (except for the page number) in the same edge slot on
3+ pages and at least half of the pages; it is dropped even with `$`, `%` or a modal verb,
unless it ends with sentence punctuation or cites Article/Section/Clause N (`Subject to
Article 12.` is kept). Lines repeated on only a minority of pages (3+) are dropped only
without `$`, `%`, shall/must/may/will/agree. Kept: a bare number inside a page (`1500`)
and edge numbers that don't track the page. Annex ids may be quoted (`SCHEDULE "B" - BENEFITS`); an
upper-case line right under an untitled annex (`APPENDIX A` / `WAGE GRID`) is its title.
A clause "title" containing `$` or `%` is treated as body, so wage rows keep amounts.
PDFs go through `pdftotext -layout` so two-column clause number/title layouts stay on one line. A clause number must belong to the current article; an untitled
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
