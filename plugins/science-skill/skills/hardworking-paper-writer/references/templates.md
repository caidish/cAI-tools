# Workspace file templates

Seed these two files in Phase 0. Keep them plain Markdown so the author can read them directly.

## revision-log.md

```markdown
# Revision log — <paper title or filename>

- Source: <path to original>
- Started: <date>
- Total prose sentences: <N>   (fill in after segmentation)
- Last reviewed: <sentence id, or "none yet">

## Sentence map

| ID   | Section | Status   |
|------|---------|----------|
| S001 | Abstract | done    |
| S002 | Abstract | edited  |
| S003 | Abstract | pending |

Status values: pending · kept (original unchanged) · edited (rewritten).

## Structure notes

_Filled during the Phase 1 whole-paper read, updated as you go. This is the supra-sentence view the sentence loop can't give you._

### Paragraph map
| Paragraph | Topic sentence (id / "buried" / "missing") | Flow into next |
|-----------|--------------------------------------------|----------------|
| Intro ¶1  | S004                                        | ok             |
| Intro ¶2  | buried (claim in S011, not S009)            | weak — no link |

### First-use map (catch use-before-define)
| Term / symbol / acronym | Defined at | First used at | Issue              |
|-------------------------|------------|---------------|--------------------|
| SNR                     | S031       | S012          | used before defined |
| $\gamma$                | S020       | S020          | ok                  |

## Decisions

### S002 — edited (Medium)
- Original: It is important to note that the results were significantly improved.
- Final:    The results improved by 23%.
- Fixes:    cut filler opener; replaced vague "significantly" with the number.

### S001 — kept
- Original: We study the dynamics of driven quantum dots.
- Final:    (unchanged — already clean and in voice)
```

Append a new `###` block per sentence as you go, newest at the top or in order — just stay consistent. The sentence map's Status column is the quick at-a-glance record of what's been reviewed; the Decisions blocks are the detail.

## style-profile.md

```markdown
# Style profile — <author / paper>

_Initial read (before any choices), then updated as the author selects._

## Voice
- Sentence length: <e.g. medium, ~22 words, low variance>
- Person/voice: <e.g. "we", active where the field allows>
- Register: <e.g. formal physics letter>
- Field conventions: <e.g. passive in Methods is fine; hedge claims>

## Punctuation
- Em-dashes: <uses / avoids>
- Semicolons, parentheticals: <...>

## Vocabulary
- Keep-list (do not change): <field terms, pet phrases>
- Kill-list (author cuts these): <...>

## Edit aggressiveness
- Observed preference: <Light / Medium / Bold>, updated as choices come in.

## Notes
- <anything the author says about how they want to be edited>
```

Treat the initial read as a hypothesis. Overwrite it with evidence as the author makes real choices — what they actually pick beats what you guessed from the prose.
