# Writer UI protocol

`scripts/writer_ui.py` is a stdlib-only local server plus a CLI that Claude Code calls from Bash. The author uses the browser; Claude uses the CLI. Every CLI command prints one JSON object. `start` records the server in `<workspace>/artifact/ui-server.json` and `~/.cache/hardworking-paper-writer/current.json`; every other command finds it from `--workspace` or that pointer, so `--workspace` is optional once started. The default port is 8766, so it can run next to a paper-review-helper session on 8765.

## Commands

| Command | Effect | Key result fields |
|---------|--------|-------------------|
| `start --workspace W [--port 8766] [--no-open] [--stop-others]` | Start (or resume) the server, open the browser | `url`, `port`, `resumed` |
| `meta [--title T] [--sections "A\|B\|C"]` | Paper title and sidebar outline (usually unnecessary: `load` sets both from `segment.py` output) | |
| `load --sentences sentences.json` | Load the sentence list. Decisions already made for sentences whose id and original text are unchanged survive a reload | `loaded`, `progress` |
| `focus --id S012` | Highlight a sentence and scroll the page to it | `current` |
| `propose --id S012 (--options opts.json \| --light T --medium T --bold T [--notes "a\|b\|c"]) [--prompt P] [--no-keep] [--text-label L] [--timeout 100] [--no-wait]` | Show the rewrite card for a sentence and wait. Cancels any pending card | see below |
| `ask [--section 02] [--sentence S012] --prompt P [--options "A\|B"] [--multi] [--text-label L] [--fields f.json] [--timeout 100] [--no-wait]` | Generic decision card (paragraph checkpoints, break points, final approval) | see below |
| `wait [--id N] [--timeout 100]` | Wait on a card (default: the latest one Claude has not heard back on) | see below |
| `say [--section 02] [--sentence S012] (--text T \| --file md)` | Post a message from Claude into the thread | `message_id` |
| `apply --id S012 --status edited\|kept\|pending [--text T \| --file f] [--choice light\|medium\|bold\|other\|keep] [--fixes F]` | Record the decision for a sentence after editing `working/`. `edited` needs the final text | `progress` |
| `profile (--file style-profile.md \| --text T)` | Show the style profile in the Style tab | |
| `export` | Write `artifact/changes.md` (every edited sentence: original, final, fixes) and `artifact/ui-transcript.md` | `written[]` |
| `status` | Server, current sentence, next pending sentence, progress, pending card | |
| `stop` | Shut the server down (state stays on disk) | |

## `propose` / `ask` / `wait` results

```json
{"status": "answered", "question_id": 7, "kind": "propose", "sentence": "S012", "section": "02",
 "answer": {"choice": "medium", "chosen_text": "The results improved by 23%.", "text": "", "values": {}},
 "messages": [], "progress": {"total": 140, "reviewed": 11, "edited": 8, "kept": 3, "pending": 129}}
```

| `status` | Meaning | What to do |
|----------|---------|------------|
| `answered` | The card was submitted | Read `answer`; apply and move on |
| `message` | Author sent chat `messages[]`; card still open | Reply with `say`, then `wait --id <question_id>` |
| `pending` | Timeout elapsed | `wait --id <question_id>` again |
| `cancelled` | A newer `propose`/`ask` replaced it | Nothing |
| `error` | Server unreachable | `status`, then `start` again (resumes) |

For a `propose` card, `answer.choice` is one of:

- `light` / `medium` / `bold` — the author picked that option; `chosen_text` is its text. If `text` is also filled, treat it as a steering note on top of the pick ("I like this one but drop the adverb").
- `keep` — keep the original; `chosen_text` is the original.
- `other` — nothing picked; `text` is either the author's own final sentence (apply verbatim) or an instruction (regenerate three options and `propose` the same sentence again). Ask once with `say` + `wait` if it is unclear which.

For an `ask` card the answer has the review-helper shape: `choice` / `choices`, `text`, `values` keyed by field id.

Timeouts: `--timeout` is seconds the server holds the request (max 3000). The default 100 s fits Claude Code's default 120 s Bash timeout. With a longer Bash timeout (pass `timeout: 1800000` to the Bash tool), use `--timeout 1500` so one call covers a long think.

## `propose` options file

```json
[
 {"level": "light",  "text": "Note that the results improved by 23%.", "note": "cuts the filler opener"},
 {"level": "medium", "text": "The results improved by 23%.",           "note": "also drops the hedge"},
 {"level": "bold",   "text": "Accuracy rose 23% (Table 2).",           "note": "recasts around the number; merges the citation"}
]
```

`text` is the exact string you will write into `working/` (LaTeX included). The browser renders it through the same LaTeX-to-Markdown cleanup as the paper, so `\cite`, `\emph` and math display properly. Prefer the file form when the sentences contain quotes or backslashes; the inline flags are fine for plain prose.

## Form cards (`--fields`)

Same as paper-review-helper: a JSON list of `{id, label, type: select|text|textarea|checkbox, options, multi, required, placeholder}`. Values come back in `answer.values` keyed by `id`.

## Sentence list (`load`)

The output of `python scripts/segment.py <paper> --out artifact/sentences.json`:

```json
{"title": "...", "format": "tex", "count": 140,
 "sections": [{"id": "01", "title": "Abstract", "level": 1, "skip": false}, ...],
 "sentences": [{"id": "S001", "section": "01", "para": 1, "kind": "prose", "line": 12,
                "text": "<source text>", "display": "<markdown for the page>"}, ...]}
```

Edit the JSON by hand before loading if the heuristic mis-split something (a broken abbreviation, a stray `\captionsetup` token). `id`s must stay unique; `para` groups sentences into paragraphs on the page; `kind: caption` renders as a figure caption; sections with `skip: true` (references, acknowledgments, appendix) are dimmed in the sidebar.

## Browser behaviour

- The page shows the selected section as running prose with every sentence clickable. Colours: amber = being discussed, green = edited, grey underline = kept, plain = not yet reviewed. Clicking a sentence opens its history (original vs final, what was fixed) above the thread.
- A new card jumps to its sentence and the Conversation tab; the header pill reads "Claude is waiting for your choice". Keys 1–4 pick an option, ⌘/Ctrl+Enter submits.
- The composer sends chat tied to the current sentence; Claude sees it on its next `wait`.
- Changes tab: every edited sentence, newest first, filtered to this section or all. Style tab: the profile Claude posted with `profile`.
- Desktop notification on a new card when the tab is hidden (permission asked on first click).
- State lives in `artifact/ui-state.json`; the page reconnects after a server restart.

## Troubleshooting

- `start` returns an error → read `artifact/ui-server.log`; `--port` to pick another port; `--stop-others` if a writer server for another paper holds the pointer.
- Page shows "Server offline" → `python scripts/writer_ui.py start --workspace W` (resumes).
- Math not rendering → the page loads marked and KaTeX from cdnjs; it needs network access once (then cached).
- Set `WRITER_UI_DEBUG=1` before `start` to log every request to `ui-server.log`.
- Regression test: `python scripts/tests/test_writer_ui.py [--browser]`.
