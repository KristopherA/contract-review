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
[{text, cite}], obligations: [{kind: obligation|prohibition|right, who, text, cite}],
definitions: [{term, text, cite}]}`.
Facts are regex-based, no model. Text is split into sentences first and the regexes run
per sentence; a sentence over 2000 chars is scanned in 2000-char windows overlapping by
200, so matching stays linear, and each fact is reported once. "Nothing shall
prevent…" saving clauses are not listed as obligations. A sentence with `shall not / must not / may not / will not / cannot` is a
prohibition, as is `No X / Nothing / Neither … shall` ("No employee shall be
disciplined"). `who` is the last noun phrase before the modal, without leading
cross-references ("See Art. 5.", "Pursuant to s. 12 of the Act …") and trailing
"i.e./e.g." asides; sentences never split after i.e., e.g., Art., No., s., Mr., Ms., Dr.
or Sec.
`--summaries FILE` (JSON `{section id: string}`, max 1 MB) adds a
`**Summary:**` line per section in Markdown; off by default. Values are collapsed to
one line, capped at 2000 chars and Markdown-escaped (including `&`; URLs and emails
become code spans, never links); too-deep JSON exits 2; unknown ids go to stderr as
warnings; any other shape exits 2. `diff --summaries` and `evolve --notes` follow the same rules; `evolve --summary-file` is escaped the same way.
Sections: only `ARTICLE/SECTION/CLAUSE/PART N`, `N` and `N.NN` headings count, plus
annexes (`LETTER OF UNDERSTANDING`, `APPENDIX A`, `SCHEDULE 1`, memorandum, addendum,
annex) which start their own top-level block; an untitled annex takes its title from a
`Re:` line. Clause numbers inside an annex are scoped to it (`Appendix A 1.01`, cited
`Appendix A, §1.01`), so a repeated `1.01` is not a duplicate; a `1. TITLE` line inside
an annex is a clause of that annex (`Schedule C 1`), never a document article. The body resumes only on an `ARTICLE N` heading, a new annex
heading, or an `N.` the table of contents lists as a main article that does not continue
the schedule's own items. Limit: a `1. TITLE` document without a TOC keeps every `N.`
after its first schedule inside that schedule. TOC entries (dot
leaders, trailing page numbers, a CONTENTS/INDEX block) and `(a)`/`(i)`/`1.` list
items stay out. Page furniture is dropped: `- N -` and `Page N of M` lines; bare
numbers at the top/bottom of pages that equal the page index plus a small offset (≤6)
on 3+ pages (explicit forms count toward the run); and running headers/footers. Lines that look like headings (`ARTICLE 3`, `1. TITLE`) are
never dropped. A line identical (except for the page number) in the same edge slot on at
least 80% of the pages (minimum 4) is dropped, except a bottom-edge full sentence with a
modal verb or `$` that is missing from at least one page; a line on every page, or at the
top, always goes. Below 80%, a repeat on 3+ pages and at least half of the pages is
dropped even with `$`, `%` or a modal verb, unless it is a bottom-edge line that ends with
sentence punctuation or cites Article/Section/Clause N (`Subject to Article 12.` on 3 of 5
pages is kept at the bottom, dropped at the top). Minority repeats (3+ pages) are dropped
unless they carry `$`, `%`, shall/must/may/will/agree, or are such a bottom-edge line.
The cases are pinned in `tests/layout_cases.py`. Kept: a bare number inside a page (`1500`)
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

## Draft 11 rules
- Headers/footers: only body pages count (a page with an inner sentence line, or 2+
  sentence lines; cover, title and TOC pages are left out). A line identical on every
  body page (at least 4) is dropped, period or not; so is a line on every page of one
  parity (at least 4) that appears on under half of the other parity.
- No-TOC schedule numbering gap: inside a schedule/annex with no TOC, a numbered heading
  that continues the main sequence (last main + 1) and not the schedule's own (item + 1)
  resumes the body. Limit: a schedule that legitimately skips to that number is misread.
- An exact repeat of the open article heading, or "ARTICLE N - continued / (cont'd)",
  with no body, is dropped. Untitled annex headings (e.g. two "LETTER OF UNDERSTANDING")
  repeat only with an explicit "continued", so separate letters stay separate.
- "X shall mean / means / includes / refers to / is defined as" sentences are
  definitions, not obligations ("includes" with a party/pronoun subject is not).
- `who` keeps at most the last 8 words.
- Durations/deadlines: spelled-out numbers include compounds ("twenty four",
  "four hundred and fifty six") and decimals ("seven point five"). "word (n)" keeps the
  bracket only when both values agree; otherwise the bracket is dropped. A bare number
  after Article/Section/s./Clause/Schedule/Appendix/§, or shaped like `1.07`, is a
  reference, not a quantity.
- pypdf log output and warnings are silenced; the page-count cross-check stays.
- Boilerplate: leading clause labels ("12.01") are stripped before matching, so the
  numbers guard no longer fails on every numbered clause; the library has generic
  collective-agreement clauses (management rights, no discrimination, severability,
  entire agreement, notices, term, no strike, gender).

## Draft 12 rules
- Boilerplate: a clause label ("12.01 ") is stripped only at the start of the section or
  of a paragraph, and only before a capital letter. A number line added mid-paragraph
  ("30.5 ...") keeps its number, so the numbers guard blocks the fold.
- Odd/even header rule: only for lines with no sentence punctuation, modal, $ or %, and
  only when a different line alternates with it in the same slot on the other parity.
  A sentence on alternate pages ("The Employer shall pay the rate in Appendix A.") is kept.
  A lone title on half the pages is still dropped by the half-of-pages header rule.
- A sentence can be both a definition and an obligation: after the definition, a second
  clause (", and the ...", "; ...") is scanned for an obligation.
- "half a day" / "half an hour" is 0.5 of the unit. A bracketed figure with no word
  before it ("(10) days") is the quantity, unless a reference word precedes it.
- "LETTER OF UNDERSTANDING - continued" joins the open letter (also "Letter of
  Understanding 2").
- An article restated with a new title merges into the first: titles are joined
  ("WAGES / HOURS OF WORK") and no sub-clause or text is dropped.
- The no-TOC gap-resume rule prints a stderr warning naming the resumed heading.

## Draft 13 rules

- **Alternating book footers:** if two different edge lines (any text, including sentences, modal verbs, $ or %, but not headings or numbered clause lines) share one slot and alternate by page parity, each on at least 80% of its own parity's body pages and on under half of the other parity's, both are dropped (draft 14: only with at least 4 body pages of each parity; digits are masked first, so "Page 4"/"Page 6" count as one line). A dropped line with a modal verb, $ or % prints a stderr warning. A lone odd-only or even-only line with no partner is still kept.
- **Boilerplate labels:** a clause label is stripped before matching only if it follows the section's own numbering (12.xx in Article 12) and the numbers go up in order. A paragraph such as "30.5 Employees shall…" blocks the fold. In a section with no numeric number (appendix, LOU), the first label sets the numbering and must end in .01 or .1; otherwise no label is stripped (draft 14).
- **Reference numbers:** after subsection, ss., sub-clause, paragraph, para., subparagraph, item, or a dotted clause number (12.01, 12.01(a)), a bracketed figure is a reference, not a duration.
- **Subjectless clause after a definition:** "X means … and shall …" gives an obligation whose subject is the defined term.
- **Restated article:** a repeated clause number in a merged restatement is cited as "N (restated)".
- **Annex ids:** "APPENDIX A-1: SHIFT" is Appendix A-1 with the title SHIFT.

## Draft 14 rules

- **Evolve section lookup:** `--section` is matched in each version on its own, in this order: exact section id (`s4`); clause number (`12`, `§12`, `Article 12`, `12.01`, `§12.01`, `Appendix A 1.02`; a cite inside a section returns that section); title equal (case-insensitive); title substring (`overtime` finds `OVERTIME AND CALL-BACK`; the tightest title wins); fuzzy title (rapidfuzz, score 70+). A renumbered clause is still found by title. If a version has no match, the previous version's section is followed by alignment. When other titles also match, the best is used and the rest are listed on stderr (`warning: ... also close: ...`). If the best candidates tie exactly (e.g. `overtime` for `OVERTIME RATES` and `OVERTIME BANKS`), evolve exits 2 and lists them; use a number or a longer title. A number query follows the number, so after renumbering it may find a different clause; query by title to follow one clause. Each timeline entry has `matched_by` (`id`, `number`, `title`, `title-substring`, `title-fuzzy`, `aligned`) and, for a cite, `matched_part`.
- **References:** a keyword with its number before a bracket is a reference, not a duration: "Clause 12 (10) days", "in Article 7, (10) days", "Appendix A (2) days".
- **Definitions:** "A day means ... and shall not include holidays" (include, exclude, mean, apply, be deemed ...) stays part of the definition; no obligation is made for the term.
