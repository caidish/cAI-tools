---
name: paper-review-helper
description: Copilot for scientific paper review. Use when reviewing a research paper (PDF/LaTeX), guiding section-by-section analysis, logging issues, and generating structured review responses. Talks to the reviewer through a local web UI (rendered sections, chat, issue log, decision cards) instead of terminal prompts.
argument-hint: <path-to-pdf-or-folder>
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - WebSearch
  - WebFetch
  - AskUserQuestion
---

# Paper Review Helper

Guide the reviewer through a structured review and produce a formal review response. The conversation runs in a **local web UI**, not in the terminal: you post each section there, the reviewer reads it rendered (math, figures, inline markers), chats, logs issues, and submits decisions on cards. You block on `ask` / `wait` until they respond.

Paths below are relative to this skill's directory. `$S` = `scripts/review_ui.py`, `$T` = `scripts/tex_tools.py`. Every command prints one JSON object; read it. Full CLI reference: [references/ui-protocol.md](references/ui-protocol.md).

## Phase 1: Setup

1. **Locate paper** from `$ARGUMENTS`. PDF → create `<paper-name>-review/`, copy it in as `original.pdf`. Folder → prefer `.tex` over PDF. Nothing found → `AskUserQuestion` for the path (the only terminal question you ask).

2. **PDF → LaTeX** (if no `.tex`): check `MATHPIX_APP_ID` and `MATHPIX_API_KEY`. If set, run `python scripts/pdf2tex.py "<pdf>" "<paper-folder>"` → `<paper-folder>/<pdf_id>/<pdf_id>.tex` with `images/`. If missing, tell the reviewer once and work from the PDF text (figures not extractable).

3. **Start the UI**: `python $S start --workspace <paper-folder>` opens the browser and prints `url`. Tell the reviewer the review happens there. If it fails (see `artifact/ui-server.log`), fall back to `AskUserQuestion` for every decision below.

4. **Outline**: with `.tex`, `python $T outline <tex> --out artifact/outline.json` then `python $S meta --outline artifact/outline.json`. Without, `python $S meta --title "<title>" --sections "Abstract|Introduction|..."`.

Workspace:

```text
<paper-folder>/
├── original.pdf, <pdf_id>/<pdf_id>.tex, <pdf_id>/images/   # sources
└── artifact/
    ├── outline.json           # sections, line ranges, figures, skip flags
    ├── sections/NN-<slug>.md  # what the reviewer sees, with markers
    ├── programs/              # math verification scripts
    ├── review-log.md          # your log (format below)
    ├── issues-major.md, issues-minor.md, ui-transcript.md   # written by `export`
    ├── REVIEW.md              # final review
    └── ui-state.json, ui-server.json, ui-server.log         # UI runtime (do not edit)
```

## Phase 2: Section-by-section

Loop over outline entries with `"skip": false` (appendix, supplement, references are skipped unless the reviewer asks). Use the outline `id` as the section id. For each:

1. **Extract**: `python $T extract <tex> --id NN --out artifact/sections/NN-<slug>.md` gives rough Markdown (math kept, `\cite` → `[cite: …]`, figures inline) plus `NN-<slug>.md.figures.json`. More than 5 paragraphs → split into `NNa`, `NNb`, … by paragraph groups (subsections are already separate entries). Without `.tex`, write the Markdown yourself from the PDF text.

2. **Mark**: read the file, `Edit` in inline markers (table below) where you see problems. Keep markers outside `$…$`. Log substantive findings: `python $S issue --severity major|minor --section NN --location "para 2" --text "…"`.

3. **Post**: `python $S section --id NN --title "<title>" --file artifact/sections/NN-<slug>.md --figures artifact/sections/NN-<slug>.md.figures.json --source "<tex> L<start>-<end>"`. Then `python $S say --section NN --text "<2-3 sentences: what this section claims and what to look at>"`.

4. **Ask** (blocks until the reviewer acts; run with a long Bash timeout such as 1800000 ms):

   ```bash
   python $S ask --section NN --prompt "Questions or concerns about this section? Rate its clarity when you are done." --options "Clear|Somewhat unclear|Confusing" --text-label "Questions / concerns" --timeout 1500
   ```

   Act on `status`:
   - `message` → the reviewer chatted. Answer it: citations → `WebSearch` (DOI, authors, title); background → `WebSearch` / `WebFetch`; math → write a script to `artifact/programs/`, run it; figures → read `images/` or use `/vision`. Reply with `python $S say --section NN --file reply.md` (or `--text`), then `python $S wait --id <question_id> --timeout 1500`. Repeat.
   - `pending` → `python $S wait --id <question_id> --timeout 1500` again.
   - `answered` → `answer.choice` is the clarity rating, `answer.text` the closing remarks. If the remarks ask something, answer with `say` before moving on.
   - Every result carries `issues`: what the reviewer logged in the UI. Acknowledge, do not re-log.

5. **Log** to `artifact/review-log.md`, then continue with the next section.

```markdown
## [Section] - [Timestamp]
### Clarity
Clear / Somewhat unclear / Confusing
### Reviewer Questions
- Q: … / A: …
### Issues Identified
- [MAJOR] … / [MINOR] …
### Tools Used
- WebSearch: "query" → finding
```

Classify: **major** = methodology flaws, unsupported claims, logical errors; **minor** = grammar, typos, unclear wording.

## Phase 3: Decision and review

1. **Decision card**: write `artifact/decision-summary.md` (issue counts from `python $S issues`, the major issues, the sections rated unclear) and post it: `python $S section --id decision --title "Decision" --file artifact/decision-summary.md`. Then ask with a form (copy `references/decision-fields.json` to `artifact/`):

   ```bash
   python $S ask --section decision --prompt "Your overall decision." --fields artifact/decision-fields.json --timeout 1500
   ```

   `answer.values` → `recommendation`, `journal`, `editor_questions`, `comments`.

2. **Export**: `python $S export` writes `issues-major.md`, `issues-minor.md`, `ui-transcript.md`.

3. **Write `artifact/REVIEW.md`** (template below), post it as `--id review --title "Draft review"`, then:

   ```bash
   python $S ask --section review --prompt "Approve this review or request changes." --options "Approve|Request changes" --text-label "What to change" --timeout 1500
   ```

   On "Request changes", revise, re-post the same id, ask again.

4. `python $S stop`. Tell the reviewer where `REVIEW.md` is.

```markdown
# Review of [Paper Title]

## Summary
[1-2 sentences]

## Overall Recommendation
[Reviewer's decision + justification]

## Major Issues
1. **Issue**: [description]
   - **Location**: Section X, paragraph Y / Equation N
   - **Impact**: [why this matters]
   - **Suggestion**: [fix, or note if unfixable]

## Minor Issues
[Grouped by type: grammar, clarity, formatting]

## Reviewer Misunderstandings Analysis
[For each confusion during review:]
- **Confusion**: [what]
- **Cause**: paper vagueness / reader knowledge gap
- **Recommendation**: [should the paper clarify?]

## Constructive Feedback
[Positives + specific improvements]

## Editor Questions Response
[If provided]
```

## Inline markers

Write these into the section Markdown; the UI renders them as colored badges the reviewer can click to log an issue.

| Marker | Meaning | Default severity |
|--------|---------|------------------|
| `[G: …]` | grammar error | minor |
| `[C: …]` | clarity issue | minor |
| `[?]` or `[?: …]` | ambiguous / unsupported claim | major |
| `[REF?]` or `[REF?: …]` | missing or questionable citation | major |
| `[EQ?]` or `[EQ?: …]` | equation to verify (place after the `$$` block) | major |

## Resuming

`start` on an existing workspace resumes its state (sections, chat, issues). Check `python $S status`, read `artifact/review-log.md`, and continue from the first section not marked `done`.
