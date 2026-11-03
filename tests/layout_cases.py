"""Synthetic layout corpus (drafts 5-10). Each case: page texts -> expected tree/facts."""
FF = "\n\f\n"
HDRS = ["Collective Agreement 2024-2027.", "Subject to Article 30 Ratification",
        "This Agreement shall be read with the Pension Plan."]
PENSION = "This Agreement shall be read with the Pension Plan"


NAMES = ["", "PURPOSE", "WAGES", "HOURS", "LEAVE", "BENEFITS", "SENIORITY", "SAFETY", "TRAINING", "OVERTIME",
         "HOLIDAYS", "GRIEVANCES", "TERM"]


def doc(*pgs):
    return FF.join(pgs)


def art(n, top=(), bottom=(), clause=None):
    """One page: ARTICLE n with one paid clause; optional edge lines."""
    clause = clause or f"{n}.01 The Employer shall pay ${n}0.00 per hour."
    return "\n".join([*top, f"ARTICLE {n}: {NAMES[n]}", clause, f"{n}.02 Clause {n} more text here.", *bottom])


def arts(n, **edges_for):
    """n pages; edges_for(page_no) -> dict(top=..., bottom=...)"""
    f = edges_for.get("f", lambda k: {})
    return doc(*(art(k, **f(k)) for k in range(1, n + 1)))


def tree_art(n):
    return [(str(k), NAMES[k]) for k in range(1, n + 1)]


def money(n):
    return [(f"${k}0.00", f"§{k}.01") for k in range(1, n + 1)]


def a12(pages, n, where):
    return arts(n, f=lambda k: {where: ["Subject to Article 12."]} if k in pages else {})


CASES = []


def case(name, text, tree, amounts=None, keep=(), gone=(), obligations=None, gone_lines=()):
    """keep/gone: substrings of the section text; gone_lines: whole lines that must not remain."""
    CASES.append(dict(name=name, text=text, tree=tree, amounts=amounts, keep=list(keep), gone=list(gone),
                      obligations=obligations, gone_lines=list(gone_lines)))


def tree_intro(n):
    return [t for k in range(1, n + 1) for t in ((str(k), NAMES[k]), (f"{k}.01", "Intro text"))]


# --- money / numbers at page edges ---
case("wage lines $10/$12/$14",
     doc(*(f"ARTICLE {n}: {NAMES[n]}\n{n}.01 Intro text.\nThe Employer shall pay ${8 + 2 * n} per hour." for n in (1, 2, 3))),
     tree_intro(3), amounts=[("$10", "§1.01"), ("$12", "§2.01"), ("$14", "§3.01")])
case("edge numbers 1500/1501/1502 kept",
     doc(*(f"ARTICLE {n}: {NAMES[n]}\n{n}.01 Units allowed:\n{1499 + n}" for n in (1, 2, 3))),
     tree_art(3), keep=["1500", "1501", "1502"])
case("page numbers 7/8/9 at offset 4 dropped",
     doc(*(art(k, bottom=[str(k + 4)]) for k in range(1, 6))),
     tree_art(5), amounts=money(5), gone=["\n5\n", "7", "8", "9"])
case("lone 1500 inside page kept",
     doc(art(1), "ARTICLE 2: WAGES\n2.01 Hours per year:\n1500\nare the cap.", art(3)),
     tree_art(3), keep=["1500"])
case("'4' footer page numbers dropped",
     doc(art(1), art(2, bottom=["2"]), art(3, bottom=["3"]), art(4, bottom=["4"])),
     tree_art(4), amounts=money(4), gone_lines=["2", "3", "4"])
case("ARTICLE N at page tops tracking the page",
     doc(*(art(k) for k in range(1, 7))), tree_art(6), amounts=money(6))
case("bare 'ARTICLE N' lines at page tops (identical once the page number is masked)",
     doc(*(f"ARTICLE {k}\n{NAMES[k]}\n{k}.01 The Employer shall pay ${k}0.00 per hour.\n{k}.02 More text here."
           for k in range(1, 7))), tree_art(6), amounts=money(6))
case("ARTICLE N at page tops under a running header",
     doc(*(art(k, top=["Sample Agreement - page %d" % k]) for k in range(1, 6))), tree_art(5), amounts=money(5),
     gone=["Sample Agreement"])

# --- Subject to Article 12 (bottom: kept below 80%; top: dropped once on half the pages,
#     and as a minority repeat because it has no $/%/modal) ---
for pages, n, where, kept in [((1, 2, 3), 3, "bottom", True), ((1, 2, 3), 5, "bottom", True),
                              ((1, 2, 3), 5, "top", False), ((2, 4, 6), 6, "bottom", True),
                              ((2, 5, 9), 12, "bottom", True), ((2, 5, 9), 12, "top", False)]:
    case(f"Subject to Article 12 on {len(pages)}/{n} {where}", a12(pages, n, where), tree_art(n),
         amounts=money(n), **({"keep": ["Subject to Article 12"]} if kept else {"gone": ["Subject to Article 12"]}))

# --- running headers ---
for where in ("top", "bottom"):
    case(f"three reviewer headers every page ({where})", arts(4, f=lambda k, w=where: {w: HDRS}), tree_art(4),
         amounts=money(4), gone=["Collective Agreement 2024", "Article 30", "Pension"], obligations=4)
for where in ("top", "bottom"):
    for txt in (PENSION, PENSION + "."):
        case(f"Pension {'with' if txt.endswith('.') else 'without'} period every page ({where})",
             arts(4, f=lambda k, w=where, t=txt: {w: [t]}), tree_art(4), amounts=money(4), gone=["Pension"],
             obligations=4)
case("header on 9 of 10 pages", arts(10, f=lambda k: {"top": [PENSION]} if k != 7 else {}), tree_art(10),
     amounts=money(10), gone=["Pension"], obligations=10)
case("bottom modal sentence on 9 of 10 pages kept",
     arts(10, f=lambda k: {"bottom": ["The Employer shall post this Agreement."]} if k != 7 else {}),
     tree_art(10), amounts=money(10), keep=["shall post this Agreement"], obligations=19)
case("2% on 3/3",
     doc(*(f"ARTICLE {n}: {NAMES[n]}\n{n}.01 Intro text.\nIncrease of 2% applies." for n in (1, 2, 3))),
     tree_intro(3), keep=["2%"])

# --- annexes ---
case("SCHEDULE B/C/E, ARTICLE style",
     "ARTICLE 1: PURPOSE\n1.01 Purpose text here.\nARTICLE 2: WAGES\n2.01 The Employer shall pay $20.00 per hour.\n"
     'SCHEDULE "B" - BENEFITS\n1.01 The Employer shall pay $5.00 per month.\n'
     "SCHEDULE C - DENTAL\n1.01 Dental text here.\nSCHEDULE E - PENSION\n1.01 Pension text here.\n",
     [("1", "PURPOSE"), ("2", "WAGES"), ("Schedule B", "BENEFITS"), ("Schedule C", "DENTAL"),
      ("Schedule E", "PENSION")],
     amounts=[("$20.00", "§2.01"), ("$5.00", "Schedule B, §1.01")])
case("SCHEDULE B/C/E, '1. TITLE' style",
     "1. PURPOSE\nPurpose text here.\n2. WAGES\nThe Employer shall pay $20.00 per hour.\n"
     'SCHEDULE "B" - BENEFITS\n1. MONTHLY\nThe Employer shall pay $5.00 per month.\n'
     "SCHEDULE C - DENTAL\n1. COVER\nDental text here.\n2. LIMITS\nLimit text here.\n"
     "SCHEDULE E - PENSION\n1. PLAN\nPlan text here.\n",
     [("1", "PURPOSE"), ("2", "WAGES"), ("Schedule B", "BENEFITS"), ("Schedule B 1", "MONTHLY"),
      ("Schedule C", "DENTAL"), ("Schedule C 1", "COVER"), ("Schedule C 2", "LIMITS"),
      ("Schedule E", "PENSION"), ("Schedule E 1", "PLAN")],
     amounts=[("$20.00", "§2"), ("$5.00", "Schedule B 1")])
case("schedule items past the last article number",
     "1. PURPOSE\nPurpose text here.\n2. WAGES\nWage text here.\nSCHEDULE A - BENEFITS\n1. DENTAL\nDental text.\n"
     "2. VISION\nVision text.\n3. DRUGS\nDrug text.\n4. LIFE\nThe Employer shall pay $9.00 per month.\n",
     [("1", "PURPOSE"), ("2", "WAGES"), ("Schedule A", "BENEFITS"), ("Schedule A 1", "DENTAL"),
      ("Schedule A 2", "VISION"), ("Schedule A 3", "DRUGS"), ("Schedule A 4", "LIFE")],
     amounts=[("$9.00", "Schedule A 4")])
case("annex followed by main body (ARTICLE keyword)",
     "ARTICLE 1: PURPOSE\n1.01 Purpose text.\nARTICLE 2: WAGES\n2.01 Wage text.\nSCHEDULE A - BENEFITS\n"
     "1.01 Dental text.\nARTICLE 3: HOURS\n3.01 The Employer shall pay $7.00 per shift.\n",
     [("1", "PURPOSE"), ("2", "WAGES"), ("Schedule A", "BENEFITS"), ("3", "HOURS")],
     amounts=[("$7.00", "§3.01")])
case("annex followed by main body ('1. TITLE' with TOC)",
     "CONTENTS\n1. PURPOSE ..... 1\n2. WAGES ..... 1\n3. HOURS ..... 2\nSchedule A ..... 2\n\n"
     "1. PURPOSE\nPurpose text here.\n2. WAGES\nWage text here.\nSCHEDULE A - BENEFITS\n1. DENTAL\nDental text.\n"
     "3. HOURS\nThe Employer shall pay $7.00 per shift.\n",
     [("1", "PURPOSE"), ("2", "WAGES"), ("Schedule A", "BENEFITS"), ("Schedule A 1", "DENTAL"), ("3", "HOURS")],
     amounts=[("$7.00", "§3")])
case("WAGE GRID title under untitled appendix",
     "ARTICLE 1: PURPOSE\n1.01 Purpose text.\nAPPENDIX A\nWAGE GRID\nStep 1 $20.00 per hour\n",
     [("1", "PURPOSE"), ("Appendix A", "WAGE GRID")], amounts=[("$20.00", "Appendix A")])
