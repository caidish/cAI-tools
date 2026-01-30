---
name: paper-review-helper
description: Copilot for scientific paper review. Use when reviewing a research paper (PDF/LaTeX), guiding section-by-section analysis, logging issues, and generating structured review responses.
argument-hint: <path-to-pdf-or-folder>
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - Grep
  - WebSearch
  - WebFetch
  - AskUserQuestion
---

# Paper Review Helper

Guide user through structured paper review, logging issues and generating formal review response.

## Phase 1: Setup

1. **Locate paper** from `$ARGUMENTS`:
   - If PDF file: create `<paper-name>-review/` folder, copy PDF into it
   - If folder: search for `.tex` first (prioritize over PDF)
   - No paper found → `AskUserQuestion`: "No paper detected. Please provide path to paper."

2. **Convert PDF → LaTeX** (if no .tex exists):

   ```bash
   # Check credentials
   [ -n "$MATHPIX_APP_ID" ] && [ -n "$MATHPIX_API_KEY" ] && echo "OK" || echo "MISSING"
   ```

   - If MISSING → notify user: "Set MATHPIX_APP_ID and MATHPIX_API_KEY for PDF→LaTeX. Proceeding with direct PDF (figures not extractable)."
   - If OK → run conversion:

   ```bash
   python ~/.claude/plugins/science-skill/skills/paper-review-helper/scripts/pdf2tex.py "<pdf_path>" "<paper-folder>"
   ```

   Output structure: `<paper-folder>/<pdf_id>/<pdf_id>.tex` with `images/` subfolder for figures.

3. **Initialize workspace**:

```text
<paper-folder>/
├── <pdf_id>/                 # Mathpix output (if converted)
│   ├── <pdf_id>.tex          # Converted LaTeX
│   └── images/               # Extracted figures
├── artifact/
│   ├── review-log.md         # Conversation log
│   ├── issues-major.md       # Major issues
│   ├── issues-minor.md       # Minor issues
│   └── programs/             # Math verification scripts
└── original.pdf              # Source PDF (if applicable)
```

## Phase 2: Section-by-Section Review

Parse LaTeX structure: `\section`, `\subsection`, `\begin{abstract}`. For each section:

1. **Chunk appropriately**:
   - Section ≤5 paragraphs: review whole
   - Section >5 paragraphs: split by `\subsection` or paragraph groups

2. **Present section** with:
   1. Section text - save the partial tex to markdown format.   
   2. Inline markers for issues (see Grammar Check Markers) in the markdown file.
   3. and provide the user with a path link to the file in the workspace.
   4. Figure refs: `[Figure X: images/<filename> - <caption>]` with a path link to the file in the workspace.


3. **Ask user** via `AskUserQuestion`:
   - "Questions about this section?"
   - "Any concerns or unclear points?"
   - "Rate clarity: clear / somewhat unclear / confusing"

4. **Respond to requests**:
   - **Citations**: `WebSearch` for DOI, author names, paper titles
   - **Background**: `WebSearch`, `WebFetch` for concepts
   - **Math check**: write script to `artifact/programs/`, run with Python/SymPy
   - **Figures**: read from `images/` folder, describe or use `/vision` skill

5. **Log** to `artifact/review-log.md`:

```markdown
## [Section Name] - [Timestamp]
### User Questions
- Q: ...
- A: ...
### Issues Identified
- [MAJOR] ...
- [MINOR] ...
### Tools Used
- WebSearch: "query" → finding
```

6. **Classify issues**:
   - **Major** → `issues-major.md`: methodology flaws, unsupported claims, logical errors
   - **Minor** → `issues-minor.md`: grammar, typos, unclear wording

**Skip Supplementary/Appendix** unless user requests.

## Phase 3: Review Generation

1. **Gather context** via `AskUserQuestion`:
   - "Overall impression? (accept / minor revision / major revision / reject)"
   - "Editor's specific questions?"
   - "Journal level? (top-tier / mid-tier / specialized)"

2. **Generate review** to `artifact/REVIEW.md`:

```markdown
# Review of [Paper Title]

## Summary
[1-2 sentences]

## Overall Recommendation
[User's decision + justification]

## Major Issues
1. **Issue**: [description]
   - **Location**: Section X, paragraph Y / Equation N
   - **Impact**: [why this matters]
   - **Suggestion**: [fix or note if unfixable]

## Minor Issues
[Grouped by type: grammar, clarity, formatting]

## User Misunderstandings Analysis
[If user had confusion during review:]
- **Confusion**: [what]
- **Cause**: paper vagueness / reader knowledge gap
- **Recommendation**: [should paper clarify?]

## Constructive Feedback
[Positives + specific improvements]

## Editor Questions Response
[If provided]
```

## Grammar Check Markers

Inline markers when presenting text:

- `[G: ...]` - grammar error
- `[C: ...]` - clarity issue
- `[?]` - ambiguous/unsupported claim
- `[REF?]` - missing or questionable citation
- `[EQ?]` - equation to verify
