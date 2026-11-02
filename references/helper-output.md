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
`sections[]` = section + `cite`, `topic_hints[]`, `dates[]`, `amounts[]`, `durations[]`.
`boilerplate_folded[]` = `{section, id, clause, score}`. Threshold: library `threshold`
(default 85) or `--threshold`; per-clause `threshold` overrides.

## diff
Array of changes `{id, kinds[], old, new, score, word_diff[]}`. `word_diff` ops are
`{op: equal|delete|insert, text}`. Alignment score = 0.35 × title similarity +
0.65 × content similarity (0-100); pairs below `--match-threshold` (default 55) are
reported as removed + added. `moved` means the relative order changed.

## evolve
`{query, timeline[]}`; each entry `{version, index, present, status, section?,
renumbered_from?, word_diff?}`. Status: baseline, first-seen, changed, unchanged,
removed, reappeared, absent. The section is followed by alignment from the
previous version, falling back to a title/number search.
