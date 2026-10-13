---
name: hardworking-paper-writer
description: Revise an academic paper sentence by sentence with the author, stripping AI writing tells (stop-slop) while preserving the author's own voice. Use this whenever the user wants to polish, tighten, edit, proofread, or "de-slop" a paper, manuscript, draft, abstract, or thesis chapter — especially when they want careful interactive sentence-level revision rather than a one-shot rewrite. Trigger on requests like "help me revise my paper", "clean up my draft", "make my writing sound less AI", "go through my abstract line by line", or when they hand over a .tex/.md/.txt/.pdf paper to improve. Talks to the author through a local web UI (the paper with the current sentence highlighted, rewrite cards, chat, change log) instead of terminal prompts.
argument-hint: <path-to-paper (.tex / .md / .txt / .pdf) or folder>
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
---

# Hardworking Paper Writer

Revise a paper one sentence at a time, with the author in the driver's seat.

The job has two halves that pull against each other. Stop-slop removes the patterns that make prose read as machine-written. But applied bluntly, those same rules sand every writer down to the same flat surface — and a paper's voice is part of what makes it worth reading. So the real task is narrower: cut the slop, keep the human. That is why this skill is slow and interactive instead of a one-shot rewrite. You are not imposing a house style; you are helping *this* author say what *they* mean, more sharply, in their own register.

Two commitments follow from that:

- **The author decides every sentence.** You propose; they dispose. Never edit prose without an explicit choice from them.
- **You get better as you go.** Every choice the author makes — and every option they reject — tells you something about their taste. Fold it back in so your later suggestions need less correction than your early ones. That is the "hardworking" part.

The conversation runs in a **local web UI**, not in the terminal: the author reads their paper there with the sentence under discussion highlighted, picks one of your rewrites (or writes their own) on a card, and chats. You block on `propose` / `ask` / `wait` until they respond. Paths below are relative to this skill's directory. `$W` = `scripts/writer_ui.py`, `$SEG` = `scripts/segment.py`. Every command prints one JSON object; read it. Full CLI reference: [references/ui-protocol.md](references/ui-protocol.md).

## The stop-slop principles

These are the patterns you are hunting for. Apply them as judgment, not as a checklist to satisfy — a sentence can break a "rule" and still be the best version.

1. **Cut filler.** Remove throat-clearing openers ("It is important to note that"), emphasis crutches ("very", "really", "significantly"), and adverbs that do no work.
2. **Break formulaic structures.** Avoid binary contrasts ("not X, but Y"), negative listings, dramatic one-word fragments, rhetorical question setups, and false agency.
3. **Prefer active voice.** Find the actor and make them the subject. "We measured" beats "measurements were taken". (Academic convention sometimes wants passive — respect the author's field norms.)
4. **Be specific.** Replace vague declaratives ("the results are significant") with the actual claim. Watch lazy extremes ("always", "never", "every") standing in for a real bound.
5. **Put the reader in the room.** Concrete beats abstract. Name the mechanism, the number, the object.
6. **Vary rhythm.** Mix sentence lengths. Two items often beat three. Avoid em-dashes if the author doesn't already use them.
7. **Trust the reader.** State findings directly. Drop the softening and the over-explanation.
8. **Cut quotables.** If a sentence sounds engineered to be tweeted, rewrite it plainly.
9. **Write for the reader, not the insider.** Unnecessary jargon is a tell of its own kind — it signals an author writing to prove membership rather than to be understood. Translate any term that has a plain equivalent, expand each acronym on first use, and unpack notation a reader can't be assumed to carry in their head. When jargon is genuinely load-bearing — a field term with no substitute — keep it, but make the sentence around it do the work of carrying someone from one subfield over. Density the argument needs, keep; density that only flatters the writer, cut.

Deeper references live in the stop-slop plugin if you need examples or the full phrase lists: `plugins/stop-slop/skills/stop-slop/references/` (`phrases.md`, `structures.md`, `examples.md`). Read them only when a specific case is unclear.

For papers, add three domain constraints on top: **never alter meaning** (a tighter sentence that changes a claim is a failure), **leave math, citations, labels, and defined terms untouched**, and **match field register** — a Nature letter and a math proof slop differently.

## Two things the sentence loop can miss

Fixing one line at a time is necessary but not sufficient. Two defects only surface when you lift your eyes from the single sentence — keep both in view throughout.

**Read as the reader, not the author.** The author knows what they mean; the reader has only the words on the page. Every so often, drop the editor's hat and read a passage cold — as someone who knows the field but has never seen this paper. Where would they stall? An undefined term, a pronoun with no clear antecedent, a claim that quietly assumes three steps the author skipped, an acronym introduced fifty lines ago — and, most often, a concept that gets *used* well before it gets *defined*. Forward references like that are nearly invisible to the author, who has the whole paper in their head, and nearly fatal to the reader, who is meeting the term for the first time with no anchor. Track where each key term, symbol, and acronym is first introduced versus where it's first used; when use precedes definition, flag it. Each of those sentences is locally fine, which is exactly why a sentence-by-sentence pass walks right past them. This reader's-eye reading is the lens behind principle 9, and it is the test for whether a rewrite actually helped: not "is this cleaner?" but "does this land for someone who isn't already inside the author's head?"

**Mind the paragraph, not just the sentence.** A paragraph has a shape, and in most academic prose that shape is general-to-specific: the opening sentence states the paragraph's claim, and everything after it earns that claim. Check that each paragraph's opener actually announces what the paragraph delivers; a buried or missing topic sentence is one of the most common structural defects, and no sentence-level edit will fix it. Then check that paragraphs connect: each should pick up where the last left off (given-new flow), so the reader never wonders why this paragraph follows that one. Watch both failure modes — a missing transition that drops the reader, and its opposite, a mechanical connective ("Furthermore", "Moreover", "Additionally") propped in place of a real logical link (that one is also slop). These are supra-sentence problems; you handle them at paragraph boundaries, not inside a single sentence's rewrite.

## Phase 0 — Set up the workspace

Intake mirrors `paper-review-helper`: take a text source, a PDF, or a folder; convert a PDF to LaTeX with Mathpix when needed; build a workspace next to the paper; start the UI.

1. **Locate the paper** from `$ARGUMENTS`. `.tex` / `.md` / `.txt` → the source. `.pdf` → the source will be the LaTeX Mathpix produces (step 2). Folder → prefer `.tex`, then `.md`, `.txt`, `.pdf`; several candidates → `AskUserQuestion` which one. Nothing found → `AskUserQuestion` for the path (the only terminal questions you ask).

2. **Convert PDF → LaTeX** (PDF sources only). Check `MATHPIX_APP_ID` and `MATHPIX_API_KEY`. If missing, tell the author: "Set MATHPIX_APP_ID and MATHPIX_API_KEY for PDF→LaTeX, or point me at a .tex/.md/.txt source" and stop — this skill edits text in place, so it needs a text source that preserves math and structure. If set, build the workspace folder first (step 4), then:

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/paper-review-helper/scripts/pdf2tex.py" "<pdf>" "<paper-stem>-revision"
   ```

   Output: `<paper-stem>-revision/<pdf_id>/<pdf_id>.tex` with `images/`. Copy it into `original/` and `working/` as `<paper-stem>.tex`; keep `<pdf_id>/` so figure paths resolve. Mathpix output carries OCR artefacts (split words, stray `\\`, mis-read symbols, `\captionsetup` leftovers) — note the conversion in `revision-log.md` and treat such tokens as noise, not the author's prose.

3. **Check for an existing revision** before creating anything. If `<paper-stem>-revision/revision-log.md` exists, this is a resume — see "Resuming".

4. **Build the workspace** as a sibling of the paper, and copy the source into both `original/` and `working/`. From here on every Edit targets `working/` only; `original/` is the safety net and the basis for the final diff.

```text
<paper-stem>-revision/
├── original/<paper>         # untouched backup — never edited
├── working/<paper>          # the live copy you edit in place
├── <pdf_id>/, original.pdf  # Mathpix output + source PDF (PDF sources only)
├── revision-log.md          # every sentence: id, status, original, chosen, fixes
├── style-profile.md         # evolving model of the author's voice + preferences
└── artifact/
    ├── sentences.json       # segment.py output (edit by hand if a split is wrong)
    ├── changes.md, ui-transcript.md               # written by `export`
    └── ui-state.json, ui-server.json, ui-server.log   # UI runtime (do not edit)
```

5. **Seed the two tracking files** from [references/templates.md](references/templates.md).

6. **Start the UI**: `python $W start --workspace <paper-stem>-revision` opens the browser and prints `url`. Tell the author the revision happens there. If it fails (see `artifact/ui-server.log`), fall back to `AskUserQuestion` for every decision below, putting each rewrite in an option `label` and the edit level plus fixes in its `description`.

## Phase 1 — Read the whole paper and profile the voice

Resist the urge to start editing immediately. Read `working/` end to end first, for two reasons: you cannot judge a sentence without its surrounding argument, and you need the author's baseline voice before you change a word of it.

While reading, fill in `style-profile.md` from the **existing prose** (this is your prior, before the author has chosen anything):

- Typical sentence length and how much it varies.
- Register: formal vs. conversational, "we" vs. passive vs. "the authors".
- Field and subfield conventions you can infer (notation density, hedging norms).
- Recurring vocabulary and any signature constructions worth preserving.
- Quirks: does the author already use em-dashes, semicolons, parentheticals? If so they are fair game; if not, don't introduce them.

This profile is what keeps your rewrites sounding like the author instead of like a generic editor. Post it so the author can see what you think their voice is: `python $W profile --file style-profile.md`. Re-post it whenever you update it in Phase 2.

The same whole-paper read is your one chance to see the structure before you start editing inside it, so map it now. Record in `revision-log.md` under **Structure notes**: each paragraph's topic sentence (or a note that it lacks one), any transition between paragraphs that drops the reader, and a running **first-use map** of key terms, symbols, and acronyms — where each is introduced and whether it's used anywhere earlier. This map is what lets you catch use-before-define defects in Phase 2, which you could never see one sentence at a time.

Then **segment** the prose into reviewable sentences with stable IDs and load them into the UI:

```bash
python $SEG working/<paper> --out artifact/sentences.json
python $W load --sentences artifact/sentences.json
```

`segment.py` follows [references/segmentation.md](references/segmentation.md) (math, citations and abbreviations never split; captions kept; math environments, tables, bibliography and the preamble skipped) and flags references, acknowledgments and appendix sections `skip: true`. Read the JSON: fix any bad split or stray token by editing the file, then `load` again. Its `text` is whitespace-normalised, so when you Edit `working/` match on a distinctive phrase rather than the whole string if the source wraps lines. Copy the id map (id → section, status) into `revision-log.md`, and tell the author (`say`) how many prose sentences there are and where you will start.

## Phase 2 — Revise sentence by sentence

Loop over unreviewed sentences in order, skipping `skip` sections unless the author asks. For each one:

**1. Judge it in context.** Read the previous and next sentence too; context prevents you from "fixing" a sentence in a way that breaks the flow into the next claim. Decide which stop-slop patterns, if any, actually apply, and whether the meaning has fragile parts (a hedge, a precise bound, a defined term) you must preserve. Read it once more as the reader: jargon with a plainer equivalent, an acronym not yet expanded, a term your first-use map says isn't defined until later. When the sentence opens or closes a paragraph, weigh its structural job too.

**2. If it is clean**, say so and confirm quickly — don't manufacture problems to look busy:

```bash
python $W propose --id S012 --prompt "This one reads clean and in your voice. Keep it?" --light "<original text>" --notes "no change" --timeout 1500
```

(Or `ask --sentence S012 --options "Keep|Show me options anyway"`.) A fast "keep" is a good outcome.

**3. Otherwise offer three versions as a spectrum**, each obeying the style profile and changing nothing about the meaning — **Light** (fix the one clearest tell, structure intact), **Medium** (a genuine rewrite for clarity and rhythm), **Bold** (rethink; may merge with a neighbour or recast the framing). Make the three meaningfully different; three near-identical rewrites waste the choice. Post them (run with a long Bash timeout such as 1800000 ms):

```bash
python $W propose --id S012 --light "..." --medium "..." --bold "..." \
  --notes "cuts the filler opener|also drops the passive|recasts around the number" --timeout 1500
```

Use `--options opts.json` when the sentences carry quotes, backslashes or math (see the protocol). The card shows the original, the three options with your notes, "Keep original", and a free-text box.

**4. Interpret the response** (`status`):

- `answered`, `answer.choice` = `light` / `medium` / `bold` / `keep` → apply that text (`keep` = no edit). If `answer.text` is also filled it is a steering note on top of the pick ("this one, but drop the adverb") — apply the pick with that adjustment, or re-`propose` if the adjustment is not obvious.
- `answer.choice` = `other` and `answer.text` is a full sentence → their final wording; apply it verbatim. If it reads as an instruction ("shorter", "keep the citation inline", "less formal") → steering, not a choice: generate three new versions guided by it and `propose` the same sentence again. Ask once (`say`, then `wait`) if it is ambiguous which they meant. This loop is where the author teaches you their taste — treat the instruction as a rule for this sentence *and* a signal for future ones.
- `message` → they chatted. Answer with `say --sentence S012`, then `wait --id <question_id>`.
- `pending` → `wait --id <question_id>` again.

**5. Apply and log.** Edit `working/` to the chosen text (skip for keep), then mirror it in the UI:

```bash
python $W apply --id S012 --status edited --text "<final text>" --choice medium --fixes "cut filler opener; active voice"
python $W apply --id S012 --status kept
```

Append the sentence to `revision-log.md` (id, original, final, pick, fixes) — the log plus `artifact/ui-state.json` is what makes a resume exact.

**6. Learn.** Update `style-profile.md` with what this choice revealed — preferred aggressiveness, words they keep or kill, how they handle hedging — per [references/preference-learning.md](references/preference-learning.md), and re-post it with `profile` when it changes meaningfully. By sentence 30 you should be proposing options that need far less steering than at sentence 3.

**7. Advance** to the next unreviewed sentence (`status` reports `next_pending`).

**Paragraph checkpoints.** After the last sentence of a paragraph, pause for the view the sentence loop can't give you: does the paragraph lead with a clear topic sentence, does it flow from the previous paragraph and into the next, does any term land before it's defined? If something's off, propose a concrete paragraph-level fix (promote or rewrite the topic sentence, add a real transition, move a definition earlier) with `ask --section NN --prompt "..." --options "Apply|Skip" --text-label "Or tell me what to do instead"`, apply it to `working/` on approval, and log it against the relevant sentence ids (re-run `segment.py` + `load` if the fix changed sentence boundaries; decisions on unchanged sentences survive a reload). Keep checkpoints lighter and rarer than the sentence loop.

**Keep the rhythm humane.** Every 20 sentences or so, offer a break: `ask --prompt "20 of 140 done — keep going or pause here?" --options "Keep going|Pause here"`. They can stop anytime; the log, profile and UI state make resuming seamless.

## Resuming

When `<paper-stem>-revision/revision-log.md` exists: `python $W start --workspace <paper-stem>-revision` resumes the UI state (sentences, decisions, chat). Read `revision-log.md` and `style-profile.md` to restore everything you learned about the author, re-read `working/` for current context, check `python $W status` for `next_pending`, then confirm the resume point with the author (`ask --options "Continue from S0NN|Start somewhere else"`) before diving back in.

## Finishing

When the author stops or you reach the end:

- `python $W export` writes `artifact/changes.md` (every edit: original, final, fixes) and `artifact/ui-transcript.md`.
- Summarise what changed (sentences reviewed, edited, kept) with `say`, and show the diff between `original/` and `working/` — `diff -u original/<file> working/<file>`, posted with `say --file` (or a section summary if it is large).
- `ask --prompt "Done for now. The edited paper is working/<file>; original/ is untouched." --options "Looks good|I want to revisit a sentence" --text-label "Which sentence?"`; on a revisit, `propose` it again.
- `python $W stop`. Leave it to the author to copy `working/` back over their source — don't overwrite their original file yourself.
