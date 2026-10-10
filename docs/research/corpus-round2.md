# Round 2 corpus: real diagrams for the nine new kinds

Status: **corpus**, the evidence the round-2 builds are checked against. Arsenal task
`t-4b992703` (issue #86). It answers open question 7 of
[`kinds-survey.md`](kinds-survey.md): the survey rested on templates and lessons, and
this file collects real figures made by teachers, researchers, public bodies and
textbooks.

## Method and limits

* **Sources.** Public pages only, preferring the people who make the figure for their own
  use: schools and national curriculum bodies, university study-skills services,
  journals, government and NHS bodies. Vendor template galleries were skipped, and the
  few kept are marked as such.
* **Nothing is copied.** Each row is one line in our own words saying what the figure
  shows. No labels, values or wording from a figure are reused in a proposal or a test.
* **How the rows were read.** The pages were found by web search and described from the
  search engine's reading of each page. Direct page fetches were blocked from this
  environment, so no figure was opened and measured here. Sizes are therefore rough
  (`~`). Where a count could not be read, the row says "not read". Before a kind is
  built, its builder should open the two or three rows marked **(check)** and count them
  properly, as the `originals/` corpus was counted for the first kinds.
* **Columns.** *Size* is the count that matters for the proposal's budget: points and
  ranges, branches and levels, variables and loops, boxes and depth, people and
  generations, steps, parts, slices, sets and regions. *Proposal* says which fields or
  limits the figure needs, and which of them it breaks.

---

## 1. Number line ([`numberline.md`](../proposals/numberline.md))

| # | Source | What it shows | Size | Proposal |
|---|---|---|---|---|
| N1 | [OpenStax, *Intermediate Algebra 2e*, 2.5 Solve linear inequalities](https://openstax.org/books/intermediate-algebra-2e/pages/2-5-solve-linear-inequalities) (textbook) | One-variable inequalities graphed on a line beside their interval notation; the four cases `>`, `≥`, `<`, `≤`. **(check)** | 1 range per line, one end bounded, the other unbounded; ~10 integer ticks | Needs open/closed ends and an unbounded end (`from` only). Uses **parenthesis/bracket** end marks, not hollow/filled dots. |
| N2 | [OpenStax, *Elementary Algebra 2e*, 2.7](https://openstax.org/books/elementary-algebra-2e/pages/2-7-solve-linear-inequalities) (textbook) | The same convention at an earlier level, with exercises that ask the reader to graph each solution set. | 1 range per line | As N1. A worksheet page stacks many independent lines; each is its own document. |
| N3 | [Oak National Academy, KS4 Higher, *Inequalities on number lines*](https://www.thenational.academy/pupils/lessons/inequalities-on-number-lines) (national curriculum body) | Lesson on drawing and reading inequalities with hollow and filled circles, including two-sided ranges such as a value between two bounds. | 1–2 ranges, ~10–20 ticks | Fits: hollow/filled dots, `from`+`to`. Its quiz contrasts "x ≤ −2" with "x > 2" on separate lines, never in one track. |
| N4 | [LibreTexts, *The pH scale*](https://chem.libretexts.org/Courses/Barstow_Community_College/Survey_of_Chemistry_and_Physics/02%3A_Structure_of_Matter/2.06%3A_Solutions/2.6.02%3A_Acids_and_Bases/2.6.2.01%3A_The_pH_Scale) (open textbook) | The 0–14 scale with neutral at 7, the acidic and basic halves, and everyday substances placed at their values. | ~12 labelled points, 2 ranges, 15 ticks | At the 12-point budget exactly. Needs labels **alternating above and below** to fit. The two halves are ranges with a shared end at 7. |
| N5 | [Alloprof, *The pH scale and acid-base indicators*](https://www.alloprof.qc.ca/en/students/vl/sciences/ph-and-ph-scale-s1038) (Quebec education non-profit) | The same scale for secondary pupils, one substance per integer from 0 to 14. | ~13 points | **Breaks** the 12-point budget by one. |

**What the corpus says.** The proposal's core (one axis, dots, ranges that are open,
closed or unbounded) is exactly what school material draws. Two gaps. First, US and
college texts mark ends with **parentheses and brackets**, not hollow and filled dots:
the proposal says the dot is "not a theme choice", but it should be a theme key
(`[numberline] ends = "dots" | "brackets"`), since both are standard and the
content is the same. Second, the pH scale (a named scale with many labelled points) sits
at or just past the 12-point limit; raise it to 15, or keep 12 and say so in the error.
No figure needed a second axis or a series, so those refusals hold. No figure put more
than two ranges in one drawing; the 4-range budget is generous.

## 2. Mind map ([`mindmap.md`](../proposals/mindmap.md))

| # | Source | What it shows | Size | Proposal |
|---|---|---|---|---|
| M1 | [Federation University Australia, *Brainstorming: mind maps* helpsheet (2025)](https://www.federation.edu.au/siteassets/files/students/study-skills/brainstorming_mind_maps_helpsheet-2025.pdf) (study-skills service) | A worked map round an everyday topic, with main branches, "twigs" off each branch and detail "nodes" off the twigs; then the same topic narrowed, giving different branches. **(check)** | ~3–5 main branches, 3 levels | Fits: depth 3 is the proposal's limit, exactly. Its three named levels (branch, twig, node) match the three levels allowed. |
| M2 | [University of Western Australia, STUDYSmarter *Mind mapping* (tn2)](https://www.uwa.edu.au/-/media/project/uwa/uwa/students/docs/studysmarter/tn2-mind-mapping.pdf) (study-skills service) | Tips sheet with an example: the key concept in the centre, ideas joined by lines **and arrows**, colour and capitals for key words. | not read | Arrows between ideas are cross-links: **refused** (concept map → `flow`). Colour per branch is theme, not content. |
| M3 | [RMIT Learning Lab, *How to create a mind map*](https://learninglab.rmit.edu.au/university-essentials/study-essentials/mind-mapping/how-create-mind-map/) (study-skills service) | Essay planning: the question in the centre; introduction, body topics and conclusion as branches, sub-points circled and attached. | ~5–7 main branches, 2–3 levels | Fits. Here the branches **do** have an order (intro → conclusion), which a mind map's clockwise placement shows only by convention. |
| M4 | [University of Portsmouth, *Mind maps* (PDF)](https://myport.port.ac.uk:443/sites/default/files/2023-01/Mind-maps.pdf) (study-skills service) | Study-skills guide to mind maps for note-taking and revision. | not read | Recorded for the size count still to do. |
| M5 | [QUT StudySmart, *Mapping your topic*](https://studysmart.library.qut.edu.au/modules/1/2/4/) (university library) | A research topic as a central node with its three key concepts round it, joined to each other. | 4 nodes | A concept map, not a mind map: the satellites are related to **each other**. The proposal is right to send this to `flow`. |

**What the corpus says.** University guides draw mind maps at the size the proposal
allows: a handful of main branches and never more than three levels below the centre,
so depth 3 and 8 main branches hold. Two features in the guides are not in the
proposal. Arrows between ideas (M2) are cross-links and stay refused, with the
concept-map suggestion, which M5 shows is a real and separate figure. **Colour and
images** per branch are recommended everywhere; colour is theme work (a per-branch
palette cycle, keyed by main branch), not a field. Essay-plan maps (M3) have an order;
the proposal's "clockwise from top right, in the order written" already keeps it,
and the docs should say that this is how to write an ordered plan.

## 3. Causal loop diagram ([`flow-loops.md`](../proposals/flow-loops.md))

| # | Source | What it shows | Size | Proposal |
|---|---|---|---|---|
| C1 | [Government Office for Science, *Foresight: Tackling Obesities, obesity system atlas* (2007)](https://assets.publishing.service.gov.uk/media/5a7b8811ed915d4147620fb2/07-1177-obesity-system-atlas.pdf) (UK government) | The full obesity system map round individual energy balance, plus smaller themed sub-maps, with a primer on reinforcing and balancing loops. | **~108 variables** in the full map; sub-maps ~10–20 | The full map is far past any budget: **refuse** and split, as the atlas itself does with its sub-maps. The sub-maps are the redrawable size. |
| C2 | [Newell, Proust, Dyball, McManus, *Seeing obesity as a systems problem*, NSW Public Health Bulletin 18(12), 2007](https://www.phrp.com.au/wp-content/uploads/2014/10/NB07028.pdf) (journal) | Fig. 2: a "fixes that fail" archetype, a balancing loop (weight-loss programmes) undermined by a reinforcing one; Fig. 3: part of the human–urban structure with loops R1 and R2. **(check)** | Fig. 2 ~4–6 variables, 2 loops; Fig. 3 ~10–15 variables, ≥2 loops | Fits: polarity on every edge, named loops, the R/B derived from parity. Archetypes (two loops sharing a variable) are the common teaching case. |
| C3 | [Chinatown childhood-obesity CLD, *PMC7895604* fig. 1 (2020)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7895604/figure/fig1) (journal, community-based research) | Residents' view of childhood-obesity factors, grouped into eleven lettered subsystems A–K, with R and B loops marked. | ~40+ variables, 11 subsystems | **Breaks** the 15-node flow budget and needs **groups** (subsystems) that the proposal does not mention. |
| C4 | [N. Osgood, *Lecture 6: Causal loop diagrams*, CMPT 858, University of Saskatchewan](https://www.cs.usask.ca/faculty/osgood/Classes/CMPT858Spring2011/LectureSlides/Lecture%206%20--%20Causal%20Loop%20Diagrams.pdf) (university course, health systems modelling) | Course slides building CLDs step by step, from a single loop to small multi-loop health examples. **(check)** for delay marks. | 2–8 variables per slide, 1–3 loops | Fits well: the teaching size. |

**What the corpus says.** Teaching material (C2, C4) is the proposal's sweet spot: four to
twelve variables, two or three named loops, signs on every arrow, the odd delay. The
6-loop budget is ample for those. Research and policy maps (C1, C3) are an order of
magnitude bigger and group their variables into **subsystems**; the existing `flow`
`groups` field should be allowed together with `loops`, and the docs should tell
authors to draw one subsystem per diagram. Many CLDs mark polarity as `s`/`o` (same,
opposite) instead of `+`/`−`; that is a theme word (`[flow] polarity = "+-" | "so"`),
not a field. Nothing in the corpus labels a loop with the wrong type, but the
derived-type check is cheap and should stay.

## 4. Argument map ([`argument.md`](../proposals/argument.md))

| # | Source | What it shows | Size | Proposal |
|---|---|---|---|---|
| A1 | [Federation University Australia, *Argument maps* helpsheet (2025)](https://www.federation.edu.au/siteassets/files/students/study-skills/argument_maps_helpsheet-2025.pdf) (study-skills service) | The contention at the top, reasons beneath, objections and rebuttals, and **"basis" boxes** of evidence under reasons. **(check)** | ~6–10 boxes, depth 3 | Fits. Basis boxes are the proposal's `note` role on a `for` point. |
| A2 | [Deakin University Study Support, *Argument mapping* (PDF)](https://deakin.edu.au/__data/assets/pdf_file/0007/2855923/Argument-mapping_Deakin-Study-Support.pdf) (study-skills service) | Mapping for essay writing: a pyramid with the contention on top, claims under it, objections and rebuttals, then how the map becomes topic sentences. | ~8–12 boxes, depth 3 | Fits. |
| A3 | [University of Melbourne Hunt Lab, *Argument mapping workshop 1* slides (2023)](https://blogs.unimelb.edu.au/huntlab/files/2023/03/AM-Workshop-1-Slides.pdf) (university research group) | Workshop exercises: students map three short everyday arguments, with worked solutions. | ~4–8 boxes each | Fits. Short arguments with **co-premises** are the usual exercise. |
| A4 | [Davies, Barnett, van Gelder, *Using computer-aided argument mapping to teach reasoning*, in *Studies in Critical Thinking* (open edition)](https://ecampusontario.pressbooks.pub/criticalthinking1234/?p=475) (academic chapter) | Fig. 1: a short argument showing the conventions: conclusion on top, reasons as shaded boxes joined by lines to it. **(check)** how objections are shown. | ~5–7 boxes | Fits. Stance shown by **colour** (reasons green); the proposal's tag + hatch keeps it in greyscale. |
| A5 | [Wikipedia, *Argument map*](https://en.wikipedia.org/wiki/Argument_map) (reference) | Worked example of an inference objection: an objection aimed at a hidden co-premise, with the unstated assumption spelled out. | ~5 boxes | **Needs an objection on a co-premise group** (on the link, not on one box). The proposal's `on` names a point, not a group. |

**What the corpus says.** Every source draws the same tree the proposal describes:
contention on top, `for` and `against` down to depth 3, rebuttal as an objection to an
objection (so no third stance), and at most about a dozen boxes; the 15-point, depth-4
budget holds. Evidence boxes (A1's basis) are common and should be named in the docs as
`role: "note"`. One feature is missing: an **inference objection** (A5), which attacks
the step from a group of co-premises to its parent rather than any one premise. Either
let `on` name a co-premise group (`on: "offer+accept"`, or an `id` on the group), or
refuse it with a message saying to state the hidden premise as a point and object to
that, which is what A5 itself recommends.

## 5. Family tree / pedigree ([`familytree.md`](../proposals/familytree.md))

| # | Source | Term used | What it shows | Size | Proposal |
|---|---|---|---|---|---|
| F1 | [Historic Royal Palaces, *Tudor family tree* (KS2–KS5)](https://www.hrp.org.uk/schools/learning-resources/tudor-family-tree-ks2-ks3-ks4-ks5/) (public body, schools) | family tree | Henry VIII, his six queens and his three children, with portraits and enquiry questions. **(check)** | ~12–16 people, 3 generations | **Breaks** "at most 3 couples per person": six marriages. Children hang from three of them; three are childless (or lost pregnancies). |
| F2 | [Westminster Abbey, *Tudors trail* teachers' notes](https://www.westminster-abbey.org/media/j3gf1e15/tudors-trail-teachers-notes.pdf) (public institution, schools) | family tree | A Tudor family tree for a school visit: the monarchs buried in the Abbey and how they are related. | ~10–15 people, 3–4 generations | Fits the people budget. Includes **half-siblings** (three children by three mothers). |
| F3 | [Library and Archives Canada, *Family tree templates*](https://www.canada.ca/content/canadasite/en/library-archives/collection/research-help/genealogy-family-history/family-tree.html) (national archive) | family tree (the chart inside is a "pedigree chart") | Printable ancestor charts: you, then 2 parents, 4 grandparents, and so on up. | **31 people, 5 generations** | **Breaks** the 4-generation limit, and is a different shape: ancestors only, no siblings, no children of a couple. The genealogist's "pedigree chart" is a binary tree, not this kind. |
| F4 | [NBC News, *The British royal family tree and line of succession*](https://www.nbcnews.com/data-graphics/uk-royal-family-tree-line-succession-graphic-rcna46931) (news graphic) | family tree | The current royal family from Elizabeth II down, with the order of succession numbered. | ~25–30 people, 4 generations | **Breaks** the 20-person budget; uses **remarriage**, and a derived order (succession) that is not the pedigree's left-to-right number. |
| F5 | [NHS England Genomics Education Programme, *Taking and drawing a family history*](https://genomicseducation.hee.nhs.uk/taking-and-drawing-a-family-history) and its [family history worksheet](https://www.genomicseducation.hee.nhs.uk/documents/family-history-worksheet/) (NHS) | pedigree | Clinical symbols for male, female, unknown sex, affected, deceased, pregnancy and miscarriage, consultand; partner, separation, consanguinity, sibship and **twin** lines. | symbol key; typical clinical pedigree 3 generations, ~10–20 people | Fits the proposal's shapes and statuses. **Missing:** twins (identical and non-identical), miscarriage, the consultand mark (distinct from proband). |
| F6 | [Bennett et al., *Standardized pedigree nomenclature update centered on sex and gender inclusivity*, J. Genetic Counseling (2022), via ELSIhub](https://elsihub.org/publication/practice-resource-focused-revision-standardized-pedigree-nomenclature-update-centered) (professional standard) | pedigree | The NSGC standard's 2022 revision: the symbol shows **gender identity**, and sex assigned at birth is an annotation under it. | standard, not a figure | **Changes `sex`**: the shape should follow gender, with assigned sex as an optional annotation. |
| F7 | [Save My Exams, *Pedigree charts* (IB Biology HL)](https://savemyexams.com/dp/biology/ib/23/hl/revision-notes/continuity-and-change/inheritance/pedigree-charts) (revision notes, written by teachers) | pedigree | Exam-style pedigrees for dominant, recessive and sex-linked traits, generations in roman numerals, people numbered in each. | ~10–15 people, 3 generations | Fits exactly: derived numbering, carrier half-shading. |

**Which name is most used.** In the sources above, **"family tree"** is the most used
term: five of them (F1–F4, and the historical survey at
[Pratt Institute, *Representations of the family tree*](https://studentwork.prattsi.org/infovis/labs/timelines/representations-of-the-family-tree/))
call the figure a family tree. **"Pedigree"** is used by three (F5–F7), all from genetics
and medicine, where it is the only term. **"Genealogical tree"** appears only in archive
catalogue titles and academic writing (for example
[Earlham College Archives, *Genealogical chart*](https://exhibits.earlham.edu/items/show/26)),
never in a teaching resource found here. In genealogy, "pedigree chart" means the
ancestor-only binary chart (F3), not this figure. By the owner's rule the kind is named
after **family tree**: `familytree` (or `family`), with `pedigree` recorded in the docs
as the clinical name for the same kind.

**What the corpus says.** Clinical and exam pedigrees (F5, F7) are the proposal's size
exactly: three generations, ten to twenty people. History and news trees break it in two
places: **one person with many partners** (six for Henry VIII, so the "3 couples" limit
must rise to at least 6, with partners laid out on one side in marriage order rather than
alternating), and **more than 20 people** in a four-generation royal tree (raise to ~30,
or keep 20 and split). Fields missing: `twins` (a pair within a couple's children,
identical or not), a `consultand` mark distinct from `proband`, and pregnancy loss as a
person `status`. The 2022 standard (F6) means `sex` should become `gender` for the
shape, with assigned sex as an optional annotation; this also answers survey question 3.
The ancestor-only chart (F3) should be **refused** with a pointer to `tree` (it is a
binary tree of ancestors), not drawn as a family tree.

## 6. Waterfall / bridge chart (feature on `chart`, no proposal yet)

| # | Source | What it shows | Size | Needs |
|---|---|---|---|---|
| W1 | [Sandwell and West Birmingham NHS Trust, *2023/24 final plan* (board paper)](https://www.swbh.nhs.uk/wp-content/uploads/2024/01/003a-Final-Plan-Boardv2.pdf) (NHS board) | A bridge from an interim deficit through stretch targets, inflation and income changes to the final plan deficit, then on to a revised plan. **(check)** | ~7–9 bars, **2 intermediate subtotals** | Needs subtotal bars mid-chart, and a whole bridge **below zero** (a deficit getting smaller). |
| W2 | [Sandwell and West Birmingham NHS Trust, *2019/20 directorate draft budget book*](https://www.swbh.nhs.uk/wp-content/uploads/2018/12/017b-Directorate-Level-First-Draft-Budget-Book-2019-20.pdf) (NHS board) | A year-on-year bridge: the revised deficit plan, reversal of one-off mitigations, normalising adjustments, to a scenario for the first month. | ~6–8 bars | Start and end totals, signed steps. |
| W3 | [Department of Health, Trust Special Administrator report vol. 3, appendix M](https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/213357/VOL-3-Appendix-M.pdf) (UK government) | From a recurrent outturn to a planned deficit, and a delivery shortfall offset by contingency releases. | ~6–10 bars, 1–2 subtotals | As W1. |
| W4 | [ICAEW, *Chart of the week: OBR forecast evaluation* (June 2026)](https://www.icaew.com/insights/viewpoints-on-the-news/2026/jun-2026/chart-of-the-week-obr-forecast-evaluation) (professional body) | From the OBR's forecast deficit for 2024/25 to the outturn, step by step through receipts, debt interest and other drivers. | ~5–7 bars | Fits a small bridge; large steps that **nearly cancel** need labels on every bar. |

**What the corpus says.** Waterfalls are real working figures in public finance and NHS
boards, not just Excel tutorials, so the deferral's condition ("wait for an original")
is met. Every original has a **start total, signed steps and an end total**, and most
add one or two **subtotals** mid-way; all have 5–10 bars. Two needs follow: a bar kind
per step (`step` | `subtotal` | `total`), with subtotals **checked** against the running
sum the way loop types are checked (an author who writes the subtotal gets it verified,
not trusted), and bridges that live **entirely below zero** (deficits). Budget: 12 bars.
Refuse a chart with no start total, and a subtotal that disagrees with the arithmetic.

## 7. Bar model / tape diagram (new kind `bars`, no proposal yet)

| # | Source | What it shows | Size | Needs |
|---|---|---|---|---|
| B1 | [NCETM, *The bar model*](https://www.ncetm.org.uk/classroom-resources/ca-the-bar-model) (national centre for maths teaching) | Guidance with examples: one bar split into parts with the whole bracketed above, and comparison bars of unequal length with the difference marked. **(check)** | 1–2 bars, 2–4 parts | Part–whole and comparison; a brace for the whole and for the difference. |
| B2 | [Oak National Academy, KS1, *Use a bar model to represent a whole partitioned into two parts*](https://thenational.academy/teachers/programmes/maths-primary-ks1/units/composition-of-numbers-0-to-5/lessons/use-a-bar-model-to-represent-a-whole-partitioned-into-two-parts) (national curriculum body) | A whole of up to five split into two parts, with the warning that pupils read unequal parts as equal unless the lengths are proportional. | 1 bar, 2 parts | Lengths **must be proportional** to the numbers. |
| B3 | [Kenmore-Tonawanda UFSD, *Eureka Math parent handbook, grade 3 module 1*](https://www.ktufsd.org/cms/lib/NY19000262/Centricity/Domain/28/Eureka%20Math%20Parent%20Handbook%20G3%20M1.pdf) (school district) | Tape diagrams for grade-3 word problems: two groups joined into a total, and equal groups for multiplication. | 1–2 tapes, 2–8 equal units | Needs **equal units** (n identical boxes, one labelled) as well as unequal parts. |
| B4 | [Harvard Extension, *Math S-305, Algebra 2, class 8* notes (2014)](https://people.math.harvard.edu/~engelwar/MathS305/Math305%20Summer%202014%20Algebra2%20Class%208.pdf) (university course for teachers) | Singapore-style bar models for ratio and multi-step problems, used to set up equations. | 2–3 bars, 3–6 units | Needs the **unknown** part marked "?", and bars aligned on a common left edge so units compare. |

**What the corpus says.** Bar models stay small: one to three bars, two to eight parts or
units, every part labelled. That supports the survey's suggestion: let `bars` in with hard
limits (3 bars, 10 parts per bar). The content is part-whole, comparison and equal units,
plus a brace over the whole or the difference and a "?" on the unknown. Length is
proportional to the number when numbers are given (B2 says this is the point), and equal
when the part is a "unit". The kind should **refuse** parts whose values do not add up to
a stated whole, and refuse a part with neither a value nor `unit`/`unknown`.

## 8. Pie / donut chart (owner question 5 in the survey)

| # | Source | What it shows | Size | Needs |
|---|---|---|---|---|
| P1 | [Byrchall High School, Wigan, *Pie charts* booklet](https://byrchall.wigan.sch.uk/_files/ugd/b5c428_576f06a4c9d146d081c6ff71bd579a17.pdf) (school) | How to draw a pie chart from a frequency table: share of the total times 360°, a protractor per sector, checking the angles sum to 360°. | 3–6 sectors | Labels per sector; angles derived from counts. |
| P2 | [Oak National Academy, Year 6, *Interpret pie charts*](https://www.thenational.academy/pupils/programmes/maths-primary-year-6/units/statistics/lessons/use-understanding-of-angles-fractions-and-percentages-to-interpret-pie-charts) (national curriculum body) | Reading pie charts through angles, fractions and percentages. | 3–5 sectors | Sectors at "nice" fractions (½, ¼); a label inside or beside each. |
| P3 | [Tax Journal, *Over 24m people receive annual tax summaries* (2014)](https://www.taxjournal.com/articles/over-24m-people-receive-annual-tax-summaries-05112014) (report on HMRC) | HMRC's personal tax summary: a pie of how the taxpayer's income tax and NICs were spent, by budget area. | **~15 sectors** | **Breaks** any small slice budget; the small slices need leader lines or a key. |
| P4 | [Full Fact, *Budget 2013: where is the money coming from, and where is it going?*](https://fullfact.org/economy/budget-2013-where-money-coming-and-where-it-going/) (fact-checker, on HM Treasury's budget charts) | The Treasury's two budget-day pies: receipts by tax and spending by function. | ~8–12 sectors each | Two pies side by side with comparable totals. |

**What the corpus says.** School pies (P1, P2) have three to six sectors and every sector
labelled; public-finance pies (P3, P4) have eight to fifteen. No **donut** chart was found
in a non-vendor source in this pass: they appear only in template galleries, so donut is
a theme variant (`[chart] pie = "pie" | "donut"`), not a separate feature. If the pie is
let in, limit it to 8 sectors, every sector labelled, values that are counts or
percentages adding to the stated total (checked), and refuse more with the suggestion of
a bar chart or `treemap`; P3's fifteen-way split is the case to refuse.

## 9. Four-set Venn (feature on [`venn`](../proposals/venn.md), owner question 6)

| # | Source | What it shows | Size | Needs |
|---|---|---|---|---|
| V1 | [Wikipedia, *Ikigai*](https://en.wikipedia.org/wiki/Ikigai), on M. Winn's 2014 figure adapted from A. Zuzunaga's 2011 "purpose" diagram (reference) | Four circles (love, skill, need, pay) in a diamond; the four pairwise overlaps named (passion, mission, vocation, profession) and the centre named. | 4 sets, **13 of 15 regions drawn, ~9 named** | **Four circles cannot draw all 15 regions**; the diamond layout cannot draw the two diagonal pairs, and names only the pairs and the centre. |
| V2 | [*Scientific Reports* (2016), PMC4890121 fig. 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC4890121/figure/f1) (journal) | Orthologous gene groups shared among four archaeal species, a count in every region. | 4 sets, **15 regions**, ellipses | Needs the four-ellipse layout and **all 15 regions**, each with a number. |
| V3 | [*Animals* 10:1649 (2020), PMC7552216 fig. 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC7552216/figure/animals-10-01649-f001) (journal) | Microbial taxa shared among four sample groups, counts in the labelled regions. | 4 sets, 15 regions | As V2. |
| V4 | [*Biodiversity Data Journal* (2022), article 69631](https://bdj.pensoft.net/article/69631/zoom/fig/7129064/) (journal) | Taxa shared among four populations of flying foxes. | 4 sets, 15 regions | As V2. |

**What the corpus says.** There are two different four-set figures. The research Venn
(V2–V4) is common in biology papers: four **ellipses**, all 15 regions, each holding a
**count**, not a sentence. The ikigai figure (V1) uses four circles, cannot show every
region, and names only the pairs it can show. The `venn` refusal ("no circle arrangement
shows every region") is right about circles and wrong about ellipses. A four-set
feature should draw the standard four-ellipse layout, allow every region, and keep region
text short (a number or a few words), since the small regions are tiny: refuse region
text longer than ~12 characters with four sets. The ikigai figure is then a four-set Venn
with some regions left empty, which costs nothing extra.

## 10. Meter: progress bar, thermometer, dial, bullet ([`meter.md`](../proposals/meter.md))

Added for arsenal task `t-df2996f3` (issue #96), after the nine above. The same limits
apply, and more strongly: these rows were found by web search and **read from the search
engine's summary of each page only**. Direct fetches failed from this environment (the
one tried, Few's specification, did not resolve), so no figure here was opened, and every
row is **(check)**. Counts are what the summaries say, not what was measured.

| # | Source | Style | What it shows | Size | Needs |
|---|---|---|---|---|---|
| G1 | [Kendall Church, *Fundraisers*](https://kendallchurch.org/fundraisers.php) (congregation) | thermometer | A match challenge toward a roof and building project, tracked on a hand-made thermometer shown in the church. **(check)** | 1 meter; a goal and an amount raised | One amount against one goal; the goal is the top of the tube. |
| G2 | [Thurston Elementary PTO, *Fundraising goal tracker*](https://thurston.a2schools.org/pto/donate/fundraising-goal-tracker) (school parents' group) | thermometer | A year's fundraising goal, the thermometer filled as families give, volunteer or join events. **(check)** | 1 meter | As G1. The page is dated: a drawing states one moment, so the date belongs in the caption. |
| G3 | [All Saints Loughborough, *Restoring the roof: Lent 2024 appeal*](https://allsaintsloughborough.org.uk/resources/restoring-the-roof-lent-2024-appeal) (parish) | thermometer | A roof appeal run in stages: a first-stage target well under the whole cost, most of it already raised. Whether a thermometer is drawn was not read. **(check)** | 1 meter, a stage target under the goal | A **target below the goal**: a mark on the tube, not a second meter. |
| G4 | [North Hertfordshire DC, *Council Delivery Plan, Q2 update*](https://democracy.north-herts.gov.uk/documents/s23849/Q2%20Update%20on%20progress%20against%20the%20Council%20Delivery%20Plan.pdf) and [*Q3 update*](https://democracy.north-herts.gov.uk/documents/s24510/Council+Delivery+Plan+Q3+update+and+projects+for+2425.pdf) (local authority) | bar | A progress bar on each council project, the share of this year's milestones complete, beside a status rating. **(check)** | one bar per project, several per page | Several bars **aligned in a panel**, each with its name; the bar says *of what* (this year's milestones only), which is a caption. |
| G5 | [Aberdeen City HSCP, *Delivery plan overview*, appendix A](https://committees.aberdeencity.gov.uk/documents/s166414/Appendix+A+-+Delivery+Plan+Overview+Y3Q3.pdf) (health and social care partnership) | bar | Programmes by status (blue, red, amber, green, plus not started and closed), with the share of projects in each. **(check)** | ~5–7 statuses | The status is named in words in the table beside the colour; a progress panel with RAG words, never colour alone. |
| G6 | [Science Learning Hub, *The fire danger sign*](https://www.sciencelearn.org.nz/resources/745-the-fire-danger-sign-and-bernie) (New Zealand science education) | dial | The semicircular roadside sign: a needle over bands from low to extreme, set each day by fire managers. **(check)** | 1 dial, 5 named bands | **Named bands round a half-circle** and one needle; no number is read at all, only the band. |
| G7 | [Museum of Fire, *From slide rule to sign post: the history of Australia's fire danger meter*](https://www.museumoffire.net/single-post/from-slide-rule-to-sign-post-the-history-of-australia-s-fire-danger-meter) and [ACM news, *Australia's new bushfire rating system*](https://www.portnews.com.au/story/7884927/everything-you-need-to-know-about-australias-new-bushfire-rating-system/) (museum; regional press) | dial | The Australian roadside meter since the 1960s: an arc of five bands and a pointer; the 2022 system cut it to four named levels plus a resting place for the needle. **(check)** | 1 dial, 4–5 named bands | As G6. The bands are **words**, and the colours repeat them. |
| G8 | [Wikipedia, *Bullet graph*](https://en.wikipedia.org/wiki/Bullet_graph), on S. Few's 2005 design (reference) | bullet | One measure as a bar, a target as a short line across it, and two to five qualitative ranges (poor, satisfactory, good) behind it in shades of one hue; designed to replace dashboard gauges. **(check)** | 1 bar, 1 target, 2–5 ranges | Bands as **tones of one ink**, not traffic lights; a linear scale from zero. |
| G9 | S. Few, *Bullet Graph Design Specification* (Perceptual Edge, 2013), `perceptualedge.com/articles/misc/Bullet_Graph_Design_Spec.pdf`, as cited by [BetterEvaluation](https://betterevaluation.org/node/1784) (evaluation methods site) | bullet | The specification: a text label, one linear scale, the featured measure, one or two comparative measures, and two to five ranges; graphs stacked with their scales aligned. Not opened: the host did not resolve. **(check)** | ~4–8 graphs stacked | **A stacked panel**, labels in one column, scales aligned. |

**What the corpus says.** Every original states **one amount against one scale**, and a
page that has several draws them **as a panel of the same style**, aligned (G4, G9);
nothing found mixes a dial with bars. That is the case for `style` on the document, not
on each meter. Fundraising thermometers (G1–G3) are single, start at zero and end at the
goal, and sometimes carry a stage target under it. Progress bars (G4, G5) come several
to a page with a status in words. Dials worth the name (G6, G7) are read by their
**named bands**, the needle saying which one; the words are on the sign and the colours
repeat them. The bullet graph (G8, G9) was designed as the honest replacement for the
dial: bands in tones of one ink, a target tick, a scale from zero. Two gaps: no
non-vendor *bullet* original was found in a public report (vendor tutorials only), so the
use case rests on the specification; and no KPI dial was found in a board paper (they
appear in vendor galleries), so the dial use case rests on the fire signs. Budget: six
meters to a panel, five bands.

---

## 11. RAG status marks: highlight reports, risk registers, board papers ([`rag.md`](../proposals/rag.md))

Added for arsenal task `t-875d4d3f` (issue #97). The same limits as section 10: found
by web search and **read from the search engine's summary of each page only**; a direct
fetch of R1 failed (the host did not resolve), so no page was opened and every row is
**(check)**. Counts are what the summaries say, not what was measured.

| # | Source | What it shows | Size | Needs |
|---|---|---|---|---|
| R1 | [Epping Forest DC, *Transformation Programme highlight report, Oct–Nov 2016*](https://rds.eppingforestdc.gov.uk/documents/s72981/Transformation%20Programme%20Oct-Nov%202016%20Highlight%20Report%20Post%20APG.pdf) and [*Transformation monitoring, Sep 2016*](https://rds.eppingforestdc.gov.uk/documents/s72494/C-034%20Transformation%20Monitoring%20Sep-16%20Rpt.pdf) (local authority) | Projects and workstreams each rated red, amber or green, red defined as significant issues needing corrective action; a second paper rates cost, delivery and benefits separately, with a sentence of reason (amber: a few of ~200 actions overdue). **(check)** | ~10–20 rows; 1 or 3 marks per row | One mark per row **with a short note saying why**; the rating's meaning stated once (a key). Per-dimension marks are a minority. |
| R2 | [Southampton City Council, *Highlight report template*](https://southampton.gov.uk/modernGov/documents/s39109/Highlight%20Report%20TEMPLATE%20ONLY.pdf) and [West Norfolk, *Project highlight report template for the Member Major Projects Board*](https://democracy.west-norfolk.gov.uk/modgov/documents/s58725/Draft%20Project%20Highlight%20Report%20template%20for%20MMPB%20BLANK_v6.1.pdf) (local authorities; templates, kept because a board uses them) | Each workstream's RAG beside a **trend**, worsening, static or improving, and a mitigation or decision field; West Norfolk ties each colour to thresholds (budget variance, weeks of slippage). **(check)** | ~5–10 workstreams | Mark, **trend in three steps**, note. |
| R3 | [West Norfolk, *OMPB meeting notes, Oct 2025*](https://democracy.west-norfolk.gov.uk/documents/s82186/OMPB%20Meeting%20Notes%20-%202025.10.16.pdf) (local authority) | The board records moving from five ratings to "just red, amber and green". **(check)** | — | **Three values** are what a board settles on; five is a known, abandoned variant. |
| R4 | [Rother DC, *decision details: corporate risk register*](https://rother.moderngov.co.uk/ieDecisionDetails.aspx?AIId=8955), [Vale of Glamorgan, *Q3 corporate risk register*](https://www.valeofglamorgan.gov.uk/Documents/_Committee%20Reports/Governance-and-Audit/2023/23-02-27/Q3-Corporate-Risk-Register.pdf) (local authorities) | A risk register: each key risk rated by RAG with the **direction of travel** since the last report; Rother's has 13 risks, two red, nine amber, two green. **(check)** | ~13 risks | A list of ~10–15 rows, mark + direction; the colours alone are the rating, which the arrow then qualifies. |
| R5 | [Shrewsbury and Telford Hospital NHS Trust, *Board Assurance Framework*, Mar 2018](https://www.sath.nhs.uk/wp-content/uploads/2018/03/22-Board-Assurance-Framework-Mar-18.pdf) (NHS trust board paper) | The board is asked to agree each risk's RAG rating and direction of travel; risks coloured by the risk matrix, arrows for increasing, decreasing or unchanged **risk**. **(check)** | ~8–12 risks | **An arrow up means the risk rose**, i.e. got worse: the opposite reading of R2's "improving". The trend must be said in words, not by arrow alone. |
| R6 | [Institute for Government, *How are government projects faring?*](https://www.instituteforgovernment.org.uk/article/comment/how-are-government-projects-faring) and [Wikipedia, *Government Major Projects Portfolio*](https://en.wikipedia.org/wiki/Government_Major_Projects_Portfolio) (think tank; reference) | The IPA's delivery confidence assessment: red (appears unachievable), amber (feasible, significant issues), green (highly likely); counts by rating across ~240 projects. Earlier years used five (amber/green, amber/red). **(check)** | 3 (or 5) ratings | Each rating has a **published definition** a key can state; the portfolio as a whole is a table, not a picture. |

**What the corpus says.** Every original is **a list**: workstreams or risks, one row
each, with its rating, often a direction of travel and almost always a sentence saying
why (R1, R2, R4, R5). The ratings are three (R3 dropped five; R6's five are older); a
blue "complete" appears in some delivery panels (corpus G5) but not in these reports. In
print the colour is the only carrier in most of them, which is the failure the kind
exists to fix: the word goes on the mark and the shape differs. The direction of travel
is ambiguous by arrow alone, since a rising arrow means *improving* in R2 and *risk
increasing* in R5, so the document says `better`/`same`/`worse` and the drawing writes
the word. Per-dimension ratings (R1's cost, delivery, benefits) are the minority and are
left out; one mark per row covers every original. Budget: 15 rows (R4: 13).

---

## Summary for the builders

| Kind | Corpus says | Change to the proposal |
|---|---|---|
| numberline | Fits; pH scale at the edge | Theme key for bracket/dot ends; points 12 → 15 |
| mindmap | Fits; depth 3 is the real maximum | None; document colour as theme, ordered plans |
| flow loops | Teaching CLDs fit; research maps are 40–100+ variables | Allow `groups` with `loops`; `s`/`o` as theme words |
| argument | Fits; evidence boxes common | Name `note` for evidence; decide inference objections |
| family tree | Clinical fits; history needs 6 partners, twins | Name it **family tree**; couples 3 → 6; `twins`; `gender` per NSGC 2022; refuse ancestor-only charts |
| waterfall | Real in NHS and public finance; 5–10 bars | `step`/`subtotal`/`total`, subtotals checked; negative bridges |
| bars | 1–3 bars, ≤ 8 parts | Proportional lengths, units, `?` unknown, braces; sums checked |
| pie | School 3–6, public finance 8–15; donut only in templates | ≤ 8 sectors, labelled, sum checked; donut as a theme variant |
| four-set Venn | Research Venns use 4 ellipses, 15 regions, counts | Four-ellipse layout; short region text |
| meter | One amount against one scale; panels of one style; dials read by named bands | `style` per document; ≤ 6 meters, ≤ 5 bands with words; bullet bands in tones |
| rag | Lists of workstreams or risks; three ratings; trend ambiguous by arrow | New kind `rag`: rows with mark, `trend` in words, note; ≤ 15 rows; no per-dimension marks |
