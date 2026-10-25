# Who else needs a diagram: a survey past the 26 kinds

Status: **survey**, the input to five proposals, not a decision. Arsenal task
`t-ae407597` (issue #77).

drawspec's kinds came from two places. `docs/kinds-wanted.md` counted 89 real study
diagrams from one set of course notes. `docs/proposals/coverage-vs-diagram-design.md`
went through a competitor's menu of 44 types. Both were written by and for people who
write technical documents. This survey asks who else writes explanatory diagrams: a
biology teacher, a law student, a policy analyst, a clinic, a systematic reviewer, a
product manager, someone planning their own month. It also asks what those people draw
that drawspec still can't.

## Method

The method is the one in `kinds-wanted.md`, applied to the public web because there is
no corpus outside software yet.

1. **Domains surveyed:** education (science, maths, history, language), business and
   strategy, operations and runbooks, product and UX, law and policy, health, data and
   research papers, and personal productivity.
2. **Evidence:** for each candidate, at least two public diagrams of that type that
   people actually use: lesson handouts, university guides, journal templates,
   government guidance, published examples. The links are recorded below with one line
   each. **None of their content is reused.** Every example in the proposals is our own.
3. **Classification** against the 26 kinds, using the same four verdicts as the earlier
   surveys:
   * **covered**: an existing kind or field draws it today;
   * **feature**: an existing kind draws it once it gains a field;
   * **new kind**: nothing draws it, and it is worth a kind;
   * **out of scope**: ruled out by *What it is not* in the README. drawspec is not a
     graph engine, not charting software, not a drawing program and not a rich-text
     system.
4. **Value** (S/M/L) is how many of the surveyed domains use the type, and how often.
   A type in every maths classroom is L. One that belongs to a single profession is S.
   **Size** (S/M/L) uses the same scale as `docs/proposals/README.md`: S means one field
   or a fixed geometry, M means a layout built from existing pieces, and L means a new
   layout family.

**This evidence is weaker than the 89 originals were.** A template on a vendor's site
shows that someone expected demand. It does not show that a real set of notes needed
the type. The proposals' rule still applies: before any of this is built, find two real
figures it would replace and draw them (*Before building any of it* in
`docs/proposals/README.md`). Several links below are vendor or template pages. They are
marked where that is all there is.

## The table

### Covered: drawspec draws these today

| Candidate | Domain | Classification | Evidence | Value | Size |
|---|---|---|---|:-:|:-:|
| Life cycle (butterfly, water, product) | education: science | **covered**: `cycle` | [Education World, butterfly life cycle lesson (stages on a circle with arrows)](https://www.educationworld.com/a_lesson/life-cycle-butterfly); [Education World, observing the stages (kindergarten circle diagram)](https://www.educationworld.com/a_lesson/Observing-Butterfly-Life-Cycle-Stages) | M | — |
| Food chain and food web | education: science | **covered**: `flow` (up to 15 organisms; a larger web is a graph and out of scope) | [EPA, food chains and food webs worksheet (marine web)](https://www.epa.gov/sites/production/files/documents/foodchainsandfoodwebs.pdf); [Lesson Planet, food web lesson plan](https://lessonplanet.com/teachers/food-web) | M | — |
| Probability tree | education: maths | **covered**: `tree` + edge `label` for each branch's probability | [Third Space Learning, probability tree diagrams (GCSE)](https://thirdspacelearning.com/gcse-maths/probability/probability-tree-diagram/); [Save My Exams, tree diagrams revision note (AQA)](https://savemyexams.com/gcse/maths/aqa/22/revision-notes/5-probability/tree-diagrams) | L | — |
| Decision tree with expected values | business, A-level | **covered**: `tree`, `decision` role, labelled edges. The convention of a circle for a chance node is not offered; a `note` role carries the expected value | [OpenLearn, decision trees and dealing with uncertainty](https://www.open.edu/openlearn/money-business/decision-trees-and-dealing-uncertainty/content-section-4.1); [Cognito, CIE business decision trees](https://cognito.org/courses/alevel/business-studies/cie/notes/SWJ5V2t0RVo/6.28-decision-trees) | M | — |
| Syntax (constituency) tree | education: language | **covered**: `tree` (S → NP VP …) | [eCampus Ontario, Essentials of Linguistics ch. 6, tree diagrams](https://ecampusontario.pressbooks.pub/essentialsoflinguistics2/chapter/from-constituency-to-tree-diagrams/); [NVCC Pressbooks, phrase-structure trees](https://pressbooks.nvcc.edu/eng200h5p/?p=282) | S | — |
| Sitemap / information architecture | product/UX | **covered**: `tree` | [Adobe XD Ideas, visual sitemap examples](https://xd.adobe.com/ideas/process/information-architecture/visual-sitemap-examples-website-designs/); [MockFlow, what is a UX sitemap](https://mockflow.com/blog/what-is-an-ux-sitemap) | M | — |
| KPI / driver tree | business, finance | **covered**: `tree` (vendor glossary evidence only) | [Hyperbots, driver tree](https://www.hyperbots.com/glossary/driver-tree); [Hyperbots, driver tree analysis](https://www.hyperbots.com/glossary/driver-tree-analysis) | M | — |
| Concept map (Novak) | education | **covered**: `flow` + edge `label` as the linking phrase, `link` for undirected cross-links | [Novak & Cañas, theory underlying concept maps (IHMC)](https://users.cs.northwestern.edu/~paritosh/papers/sketch-to-models/Novak-Canas-TheoryUnderlyingConceptMapsHQ.pdf); [Framingham State library guide, concept mapping](https://libguides.framingham.edu/conceptmapping) | L | — |
| Logic model | policy, public health | **covered**: `flow` + `groups` per column (inputs → activities → outputs → outcomes); `columns` when there are no links | [CDC, logic models](https://www.cdc.gov/evaluation/logicmodels/); [NACCHO, logic model quick guide](https://www.naccho.org/uploads/downloadable-resources/LMQuickGuide.pdf) | M | — |
| Theory of change | policy, non-profit | **covered**: `flow` + `groups`; the "accountability ceiling" is a `band` | [NPC, theory of change in ten steps](https://www.thinknpc.org/wp-content/uploads/2018/07/Theory-of-change2.pdf); [Australian Department of Finance, outcome-mapping template](https://www.finance.gov.au/sites/default/files/2021-11/Template%201_Theory%20of%20change%20%28outcome%20mapping%29_0.doc) | M | — |
| How a bill becomes law | law, civics | **covered**: `lanes` (chamber, chamber, executive) | [Dearborn Schools, how a bill becomes a law flow chart](https://iblog.dearbornschools.org/murrayr/wp-content/uploads/sites/434/2017/12/How-a-Bill-Becomes-a-Law-Flow-Chart-2017.pdf); [Alabama ACCESS government course task](https://accessdl.state.al.us/AventaCourses/access_courses/government_ua_v17/04_unit/04-04/04-04_task1.docx) | M | — |
| Clinical algorithm / care pathway | health | **covered**: `flow` with `decision`s (split by the 15-node budget into overview + detail, as the guidelines themselves do) | [NICE NG101, supplement 3: pathway algorithm](https://nice.org.uk/guidance/ng101/documents/supporting-documentation-3); [NCBI Bookshelf, NG101 evidence review figure](https://https.ncbi.nlm.nih.gov/books/NBK576827/bin/niceng101erbm6.pdf) | L | — |
| PRISMA flow diagram | research papers | **covered**: `flow` + `bands` for the phases (identification, screening, included) + `aside` edges to the exclusion boxes. Counts stay in the text; drawspec does not add them up | [PRISMA 2020 flow diagram (official templates)](https://www.prisma-statement.org/prisma-2020-flow-diagram); [PMC, PRISMA 2020 statement figure 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC8005924/figure/f1) | L | — |
| CONSORT flow diagram | research papers, health | **covered**: as PRISMA; two arms are two branches, phases are `bands` | [CONSORT 2010 statement (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3043330/); [JBJS, CONSORT 2010 flow diagram template](https://sites.jbjs.org/Documents/CONSORT-2010-Flow-Diagram-MS-Word.doc) | M | — |
| SWOT | business | **covered**: `matrix` 2×2 with `rows` internal/external and `columns` helpful/harmful; or `board` with `rows` | [Asana, SWOT analysis examples](https://asana.com/resources/swot-analysis); [Process Street, SWOT template](https://www.process.st/swot-analysis-template/) | L | — |
| Eisenhower (urgent/important) matrix | personal, business | **covered**: `quadrant` when tasks are placed; `matrix` when each cell holds a list | [Atlassian, Eisenhower matrix template](https://www.atlassian.com/software/confluence/templates/eisenhower-matrix); [101 Planners, Eisenhower matrix](https://www.101planners.com/the-eisenhower-matrix/) | M | — |
| Stakeholder power/interest grid | business, policy | **covered**: `quadrant` | [Lucid, stakeholder map example](https://www.lucidchart.com/pages/templates/stakeholder-map-example); [Vaia, stakeholder mapping](https://vaia.com/en-us/explanations/business-studies/project-planning-management/stakeholder-mapping) | M | — |
| Porter's five forces | business education | **covered**: `flow` with a `centre` node (rivalry) and four spokes | [Strategic Management Insight, five forces (automotive example)](https://www.strategicmanagementinsight.com/tools/porters-five-forces.html); [ConceptDraw, five forces diagram](https://www.conceptdraw.com/examples/porters-diagram) | M | — |
| Business model canvas | business | **covered** (to be confirmed by drawing one): `matrix` with spanning cells, a 10 × 3 grid. A cell holds a lead and a detail, not a bulleted list | [SCORE, business model canvas template](https://www.score.org/resource/template/business-model-canvas-template); [Businesslink, creating your business model](https://businesslink.ca/blog/creating-your-business-model) | M | — |
| Empathy map | product/UX | **covered**: `matrix` 2×2 (says/thinks/does/feels) | [BCIT, UX empathy map](https://www.bcit.ca/files/knowledge-base/files/pdfs/bcit-ux_empathy-map.pdf); [ASU Work+ empathy-map worksheet](https://theworkpluscollective.asu.edu/media/212/download) | S | — |
| RACI matrix | operations, projects | **covered**: `matrix` (tasks × roles, cell `group` = R/A/C/I, with a `key`) | [CIO, the RACI matrix](https://www.cio.com/article/287088/project-management-what-is-raci-and-how-does-it-improve-clarity.html); [PM Study Circle, RACI matrix examples](https://pmstudycircle.com/raci-matrix-examples/) | M | — |
| SIPOC | operations, Six Sigma | **covered**: `columns` (five items) or `matrix` | [TechTarget, SIPOC diagram](https://www.techtarget.com/searchcio/definition/SIPOC-diagram-suppliers-inputs-process-outputs-customers); [ProjectManager, SIPOC how-to](https://www.projectmanager.com/blog/sipoc-diagram) | S | — |
| Now / next / later roadmap | product | **covered**: `board` (three columns of cards) | [ProdPad, now-next-later roadmap](https://www.prodpad.com/glossary/now-next-later-roadmap/); [Aha!, introducing the now, next, later roadmap](https://www.aha.io/blog/introducing-the-now-next-later-roadmap) | M | — |
| Punnett square | education: biology | **covered**: `matrix` (gametes as `rows`/`columns`, genotypes in cells, phenotype as the cell `group`) | [Open Genetics, Punnett squares 3:1](https://opengenetics.pressbooks.tru.ca/chapter/punnett-squares-31-ratio/); [LibreTexts, Punnett squares](https://bio.libretexts.org/Bookshelves/Genetics/Introduction_to_Genetics_(Singh)/01:_Mendels_First_Law_and_Meiosis/1.05:_Punnett_Squares_-_3-1_Ratio) | M | — |
| Verb-tense timeline | education: language | **covered**, roughly: `timeline` + `at` + `spans`. It reads better as a `numberline` (below), which has "now" at zero and ranges that stay open | [UTS, present perfect tense handout (timelines)](https://www.uts.edu.au/sites/default/files/Grammar%202B%20Verb%20Tenses%20Handout%20-%20Present%20Perfect%20Tense.pdf); [English Lessons Brighton, all tenses on one timeline](https://englishlessonsbrighton.co.uk/all-english-tenses-timeline-infographic/) | M | — |

### Feature: an existing kind draws it once it gains a field

| Candidate | Domain | Classification | Evidence | Value | Size |
|---|---|---|---|:-:|:-:|
| **Causal loop diagram** | policy, health systems, sustainability, business, systems-thinking courses | **feature**: `flow` + edge `polarity` (+/−), `delay`, named `loops` whose reinforcing/balancing type is checked against the polarities → [`flow-loops.md`](../proposals/flow-loops.md) | [Wikipedia, causal loop diagram](https://en.wikipedia.org/wiki/Causal_loop_diagram); [Politecnico di Milano, ER Forum 2025 causal loop diagrams](https://annabernasconi.faculty.polimi.it/wp-content/uploads/ER_Forum_2025___Causal_Loop_Diagrams.pdf); [Creately, causal loop diagram guide](https://creately.com/guides/causal-loop-diagram/) | M | S |
| Cladogram / tournament bracket | education: biology; sport, personal | **feature**: `tree` + a `bracket` style (leaves aligned on one line, square elbows, internal nodes unboxed) | [Boston University GK-12, building a cladogram](https://www.bu.edu/gk12/eric/cladogram.pdf); [Cornell CIBT, evolution tree teacher guide](https://prod.cibt.cornell.edu/workshops_and_summer_programs/0611stanys/EvolTreeTeacher.pdf); [Lucid, tournament brackets 101](https://lucidchart.com/blog/tournament-brackets-101) | M | S |
| Service blueprint | product/UX, public services | **feature**: `lanes` + named `lines` between lanes (line of interaction, of visibility, of internal interaction) | [Digital Public Services Wales, service blueprint](https://digitalpublicservices.gov.wales/node/706); [Pratt IXD, service blueprint](https://ixd.prattsi.org/2019/09/service-blueprint/); [Utah Education Network, services management ch.](https://uen.pressbooks.pub/servicesmgt/?p=55) | S | S |
| Value stream map | operations, lean | **feature**: `flow` + a lead-time ladder under the steps (wait and work time per step). Low priority: `gantt` already states the same waits | [Smartsheet, how to create a value stream map](https://www.smartsheet.com/content/create-value-stream-map); [Learn Lean Sigma, how to create a VSM](https://www.learnleansigma.com/process-mapping/how-to-create-a-vsm/) | S | M |
| Waterfall / bridge chart | business, finance course notes | **feature** (deferred already): `chart` + a `bridge` mark. The deferral asked for originals, and finance teaching material supplies them. The scope question is still open | [Vertex42, waterfall chart template](https://www.vertex42.com/ExcelTemplates/waterfall-chart.html); [AccountingWEB, waterfall charts in Excel](https://www.accountingweb.co.uk/node/136275); [Ticker League, waterfall vs bridge](https://tickerleague.com/learn/waterfall-and-bridge-charts) | M | S |
| Four-set Venn (the "ikigai" figure) | personal, careers | **feature** on `venn`, which refuses four sets on purpose. Four ellipses can show all 15 regions, but most four-set figures in circulation leave out two of the regions | [Figma, ikigai diagram template](https://www.figma.com/templates/ikigai-diagram/); [Piktochart, ikigai four-circle Venn](https://piktochart.com/templates/diagrams/2674-ikigai-four-circle-venn-diagram/); [Lumen, choosing and using graphics](https://content.one.lumenlearning.com/businesscommunication/chapter/apply-it-choosing-and-using-graphics/) | S | M |

### New kind: nothing draws it, and it is worth a kind

| Candidate | Domain | Classification | Evidence | Value | Size |
|---|---|---|---|:-:|:-:|
| **Number line** (inequalities, intervals, spectra) | education: maths (every year from age 6), language (tenses), policy (a spectrum of positions) | **new kind** `numberline` → [`numberline.md`](../proposals/numberline.md). `timeline` has `at`, but it has no open or closed ends, no unbounded ranges and no ticks, and "when" is the wrong word for x < 3 | [Third Space Learning, inequalities on a number line](https://thirdspacelearning.com/us/math-resources/topic-guides/algebra/inequalities-on-a-number-line/); [TutorChase, inequalities on a number line (GCSE)](https://www.tutorchase.com/notes/aqa-gcse/maths-higher/2-5-2-inequalities-on-a-number-line); [Virginia DOE, grade 6 instructional plan](https://doe.virginia.gov/home/showpublisheddocument/17314/638037671724770000) | L | S |
| **Mind map** | education (revision notes), personal, business (brainstorms), history | **new kind** `mindmap` → [`mindmap.md`](../proposals/mindmap.md). A `tree` is ranked from a root at one edge; a mind map radiates from a centre to both sides | [University of Vermont, mind map notes](https://www.uvm.edu/sites/default/files/Center-for-Academic-Success/Tutoring%20Center/Additional%20Academic%20Resources/Mind_Map_Notes.pdf); [Millersville University, mind maps handout](https://www.millersville.edu/learningservices/files/mind-maps.pdf); [MIT OCW ESD.34, mind mapping lecture notes](https://live.ocw.mit.edu/courses/esd-34-system-architecture-january-iap-2007/resources/mind_mapping/) | L | M |
| **Argument map** (and the Toulmin layout, merged into it) | law, policy, philosophy, debating, research discussion | **new kind** `argument` → [`argument.md`](../proposals/argument.md). A `tree` cannot say *for* and *against*, or that two premises only count together | [Wikipedia, argument map](https://en.wikipedia.org/wiki/Argument_map); [Deakin University, argument mapping study guide](https://deakin.edu.au/__data/assets/pdf_file/0007/2855923/Argument-mapping_Deakin-Study-Support.pdf); [OpenWA Pressbooks, visualizing logic](https://openwa.pressbooks.pub/howtothinkforyourself/chapter/%C2%A75-visualizing-logic/); [Lumen, Toulmin's argument model](https://courses.lumenlearning.com/suny-jeffersoncc-englishcomp2kscopexmaster/chapter/toulmins-argument-model/) | M | M |
| **Pedigree / family tree** (genogram's structural part) | health (genetic counselling), education: biology, history, personal genealogy | **new kind** `pedigree` → [`familytree.md`](../proposals/familytree.md). A `tree` gives a child one parent; here a child comes from a couple, and partners share a row | [SLCC College Biology, pedigree analysis](https://slcc.pressbooks.pub/collegebiology1/?p=1074); [Creately, autosomal recessive pedigree](https://creately.com/diagram/example/TXlsluzIDd6/autosomal-recessive-trait-pedigree-chart); [Creately, genogram in psychology](https://creately.com/guides/genogram-in-psychology/); [Pabau, genogram example](https://pabau.com/blog/genogram-example/) | M | L |
| Bar model / tape diagram | education: primary maths (Singapore, Common Core) | **new kind** `bars`, not proposed yet: a whole bar split into labelled parts, comparison bars and a brace for the unknown. Each length stands for a number, so it raises the same scope question `treemap` did | [AlgebraKiT, bar model method](https://help.algebrakit.com/pages/1150-model-method/); [ConceptViz, what is a tape diagram](https://conceptviz.app/blog/what-is-a-tape-diagram) | M | M |

### Out of scope, and worth saying so

| Candidate | Domain | Classification | Evidence | Value | Size |
|---|---|---|---|:-:|:-:|
| Free-body diagram | education: physics | **out of scope**: drawing program. The direction and relative length of each arrow *are* the content | [The Physics Classroom, drawing free-body diagrams](https://azure.physicsclassroom.com/video-tutorial/newtons-laws/drawing-free-body-diagrams); [Nagwa, free-body diagrams lesson plan](https://www.nagwa.com/en/plans/546171698176) | — | — |
| Circuit schematic | education: physics, engineering | **out of scope**: drawing program and symbol library. The topology alone fits a `flow`, but nobody reads a circuit that way | [LabXchange, series and parallel circuits handout](https://www.labxchange.org/library/items/lb:LabXchange:97de1064:lx_document:1); [The Physics Classroom, series vs parallel](https://www.physicsclassroom.com/video-tutorial/electric-circuits/comparing-series-and-parallel-circuits) | — | — |
| Forest plot | research papers, health | **out of scope**: charting (confidence intervals, log ratio scales, weights) | [PMC, how to interpret the forest plot](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10947628/); [NCCMT, interpreting meta-analysis graphs](https://www.nccmt.ca/resources/search/166) | — | — |
| Pie chart | education: maths (Year 6), business | **out of scope**: charting. "Parts of one known total" is `treemap`. Whether to keep refusing it is an owner question (below) | [Oak National Academy, interpret pie charts (Year 6)](https://www.thenational.academy/pupils/programmes/maths-primary-year-6/units/statistics/lessons/use-understanding-of-angles-fractions-and-percentages-to-interpret-pie-charts); [Coding Ireland, pie charts and proportional representation](https://codingireland.ie/ViewLesson/pie-charts-and-proportional-representation-20571/8149) | — | — |
| Habit tracker / calendar grid | personal | **out of scope**: a form to fill in, not an explanation, and it needs dates, which `gantt` already declined. A finished month of ticks is a `matrix` + `scale` | [Gumroad, printable monthly habit tracker](https://livelifesuccessfull.gumroad.com/l/printable-month-habit-tracker); [Payhip, A4 habit tracker](https://payhip.com/b/M9EfD) | — | — |
| Genogram emotional-relationship lines | health: family therapy | **out of scope** for `pedigree` v1: about a dozen line patterns (close, conflicted, cut off …) on a mesh between any two people. Revisit with an original | [Creately, genogram symbols](https://static2.creately.com/guides/genogram-symbols); [Creately, counselling genogram examples](https://www.creately.com/guides/counseling-genogram-editable-templates-and-examples) | — | — |

**Tally:** 25 covered, 6 features, 5 new kinds (4 proposed), 6 out of scope.

The result is reassuring. Most of what people outside software draw is already
drawable: a cycle, a tree, a flow, a 2×2, a board. The rows marked covered matter as
much as the gaps. Each one is a reference document and a gallery entry worth adding, so
that a teacher or an analyst can see that their figure is there.

## Ranked shortlist

The ranking is by value to the widest set of readers first, then by smallest size.

| Rank | Candidate | Verdict | Value | Size | Proposal |
|---:|---|---|:-:|:-:|---|
| 1 | Number line | new kind `numberline` | L | S | [`numberline.md`](../proposals/numberline.md) |
| 2 | Mind map | new kind `mindmap` | L | M | [`mindmap.md`](../proposals/mindmap.md) |
| 3 | Causal loop diagram | feature: `flow` + `polarity`/`delay`/`loops` | M | S | [`flow-loops.md`](../proposals/flow-loops.md) |
| 4 | Argument map | new kind `argument` | M | M | [`argument.md`](../proposals/argument.md) |
| 5 | Pedigree / family tree | new kind `pedigree` | M | L | [`familytree.md`](../proposals/familytree.md) |
| 6 | Cladogram / bracket | feature: `tree` bracket style | M | S | [`tree-bracket.md`](../proposals/tree-bracket.md) (built) |
| 7 | Bar model | new kind `bars` | M | M | — (scope question 5) |
| 8 | Waterfall | feature: `chart` `bridge` | M | S | — (already deferred; scope question 4) |
| 9 | Service blueprint | feature: `lanes` + `lines` | S | S | — |
| 10 | Four-set Venn | feature: `venn` | S | M | — (question 6) |
| 11 | Value stream map | feature: `flow` ladder | S | M | — |

**Covered types worth a reference document**, because a reader in that domain would not
guess the kind: PRISMA and CONSORT (`flow` + `bands` + `aside`), the logic model and
theory of change (`flow` + `groups` + a `band`), Porter's five forces (`flow` +
`centre`), the business model canvas (`matrix` spans), the Punnett square (`matrix`),
SWOT and the empathy map (`matrix`), and the probability tree (`tree` + labels). Each is
one JSON file in `docs/reference/` and one row in the guide's *choosing a kind* table.
Nothing else needs to be built for them.

## Open questions for the owner

1. **`numberline`: a kind, or `timeline` + an axis?** It reuses most of `timeline`'s
   layout. Proposed as its own kind, because `timeline` reads as *when*, `at` there
   means a date-like position, and an inequality is not a history. The cheaper
   alternative is a `timeline` with `axis` and open-ended `spans`.
2. **`mindmap` budget.** Real mind maps run to 20–40 nodes. `tree` stops at 15.
   Proposed: 8 main branches, 30 nodes and depth 3, on the grounds that a mind map's
   leaves are single phrases on a line, not boxes. Confirm, or hold it to `tree`'s 15.
3. **`pedigree` uses a field whose value picks a shape.** `sex: male | female | unknown`
   selects square, circle or diamond. That is the clinical standard, and it is data
   rather than appearance, much as `status` picks a pill. Accept it, or ask for a
   neutral `marker`? Also: name it `pedigree` (clinical) or `family` (genealogy)?
4. **Waterfall now has originals.** Finance teaching material uses it constantly. Lift
   the deferral (`chart` + `bridge`, size S), or keep it out because a running total is
   arithmetic drawspec would do for the reader?
5. **Bar models and pie charts** both make a size stand for a number. `treemap` and
   `sankey` were let in with hard limits. Do the same for a primary-school bar model
   (a few parts, every part labelled), and keep the pie out because `treemap` says the
   same thing?
6. **Four sets in `venn`.** The refusal says four-set figures belong in a `matrix`. The
   ikigai figure is popular and draws only some of the regions. Keep the refusal?
7. **Evidence before building.** This survey rests on public templates and lessons, not
   on a corpus. Is there a second real corpus to collect, such as a teacher's slides, a
   policy unit's briefs or a clinic's leaflets, the way `originals/` was for the first
   kinds?
