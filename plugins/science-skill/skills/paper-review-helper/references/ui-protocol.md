# Review UI protocol

`scripts/review_ui.py` is a stdlib-only local server plus a CLI that Claude Code calls from Bash. The reviewer uses the browser; Claude uses the CLI. Every CLI command prints one JSON object. `start` records the server in `<workspace>/artifact/ui-server.json` and `~/.cache/paper-review-helper/current.json`; every other command finds it from `--workspace` or that pointer, so `--workspace` is optional once started.

## Commands

| Command | Effect | Key result fields |
|---------|--------|-------------------|
| `start --workspace W [--port 8765] [--no-open] [--stop-others]` | Start (or resume) the server, open the browser | `url`, `port`, `resumed` |
| `meta [--title T] [--outline outline.json \| --sections "A\|B\|C"]` | Paper title and sidebar outline | |
| `section --id NN --title T --file md [--figures figs.json] [--source S]` | Show a Markdown file as the current section; the previous open section becomes `done` | `section` |
| `say [--section NN] (--text T \| --file md)` | Post a message from Claude into the section thread | `message_id` |
| `ask [--section NN] --prompt P [--options "A\|B"] [--multi] [--text-label L] [--fields f.json] [--timeout 100] [--no-wait]` | Show a decision card and wait. A new `ask` cancels any pending one | see below |
| `wait [--id N] [--timeout 100]` | Wait on a question (default: the latest one Claude has not heard back on) | see below |
| `issue --severity major\|minor [--section NN] [--location L] --text T [--marker G\|C\|?\|REF\|EQ]` | Log an issue found by Claude | `issue_id` |
| `issues [--new]` | List issues; `--new` = only ones not yet delivered to Claude | `issues[]` |
| `done [--section NN]` | Mark a section reviewed | |
| `export` | Write `artifact/issues-major.md`, `issues-minor.md`, `ui-transcript.md` | `written[]` |
| `status` | Server, current section, pending question, counts | |
| `stop` | Shut the server down (state stays on disk) | |

## `ask` / `wait` results

```json
{"status": "answered", "question_id": 3, "section": "02",
 "answer": {"choice": "Somewhat unclear", "choices": ["Somewhat unclear"], "text": "free text", "values": {"field_id": "value"}},
 "messages": [], "issues": [ {"id": 1, "severity": "major", "section": "02", "location": "Eq. 1", "text": "…", "source": "user"} ]}
```

| `status` | Meaning | What to do |
|----------|---------|------------|
| `answered` | The card was submitted | Read `answer`; move on |
| `message` | Reviewer sent chat `messages[]`; card still open | Reply with `say`, then `wait --id <question_id>` |
| `pending` | Timeout elapsed | `wait --id <question_id>` again |
| `cancelled` | A newer `ask` replaced it | Nothing |
| `error` | Server unreachable | `status`, then `start` again (resumes) |

`issues[]` in any result are reviewer-logged issues not yet delivered; they are marked delivered once returned.

Timeouts: `--timeout` is seconds the server holds the request (max 3000). The default 100 s fits Claude Code's default 120 s Bash timeout. With a longer Bash timeout (pass `timeout: 1800000` to the Bash tool), use `--timeout 1500` so one call covers a long read.

## Form cards (`--fields`)

A JSON list; each field renders in order above the Submit button.

```json
[
 {"id": "recommendation", "label": "Overall recommendation", "type": "select",
  "options": ["accept", "minor revision", "major revision", "reject"], "required": true},
 {"id": "journal", "label": "Journal level", "type": "select", "options": ["top-tier", "mid-tier", "specialized"]},
 {"id": "editor_questions", "label": "Editor's questions", "type": "textarea", "placeholder": "Paste them here"},
 {"id": "comments", "label": "Anything else", "type": "textarea"}
]
```

Types: `select` (add `"multi": true` for several), `text`, `textarea`, `checkbox`. Values come back in `answer.values` keyed by `id`. `--options` and `--text-label` may be combined with `--fields`.

## Section Markdown

- Standard Markdown; math as `$…$`, `$$…$$`, `\(…\)`, `\[…\]` (KaTeX). Markers written inside math are hoisted out after the math.
- Images: relative paths resolve against the Markdown file's folder inside the workspace; absolute paths inside the workspace are rewritten to served URLs. Files outside the workspace cannot be shown.
- `--figures` JSON: `[{"path": "...", "caption": "...", "label": "fig:one"}]`. Figures already inline in the Markdown are not shown twice.
- `[cite: key]` and `[ref: label]` (as produced by `tex_tools.py extract`) render as muted tags.
- A leading heading equal to the section title is hidden in the UI.

## Browser behaviour

- New question → jumps to its section and the Conversation tab; the header pill reads "Claude is waiting for your decision". Other sections stay browsable; a banner links back.
- Composer sends chat (⌘/Ctrl+Enter). Issues tab logs, edits, deletes issues; clicking a marker badge pre-fills the form.
- Desktop notification on a new question when the tab is hidden (permission asked on first click).
- State lives in `artifact/ui-state.json`; the page reconnects after a server restart.

## Troubleshooting

- `start` returns an error → read `artifact/ui-server.log`; `--port` to pick another port; `--stop-others` if a server for another paper holds the pointer.
- Page shows "Server offline" → `python scripts/review_ui.py start --workspace W` (resumes).
- Math not rendering → the page loads marked and KaTeX from cdnjs; it needs network access once (then cached).
- Set `REVIEW_UI_DEBUG=1` before `start` to log every request to `ui-server.log`.
