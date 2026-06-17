# Learning the author's preferences

The point of going sentence by sentence is not just to fix sentences — it's to build a model of how *this* author wants to write, so your suggestions converge on their taste. A well-run session needs heavy steering at sentence 3 and almost none by sentence 30. This file is about how to get there.

## Read both the choice and the rejection

Every `AskUserQuestion` answer carries two signals:

- **What they picked** tells you the edit aggressiveness and wording they want.
- **What they passed over** tells you what to stop proposing. If they keep rejecting the Bold option, stop leading with bold rewrites. If they always take Light, they want a proofread, not a rewrite — shrink your edit distance across the board.

Their free-text steers ("shorter", "keep 'utilize', it's the field term", "don't merge sentences") are the strongest signal of all. Treat each as a standing rule, not a one-off.

## What to track in style-profile.md

Update these after meaningful choices (not every single sentence — when something is revealed):

- **Edit aggressiveness:** running sense of Light / Medium / Bold preference. Bias future option-spreads toward it.
- **Voice markers:** "we" vs passive vs "the authors"; first vs third person. Match it.
- **Vocabulary:** words they insist on keeping (field terms, pet phrases) and words they consistently cut. Maintain a keep-list and a kill-list.
- **Punctuation:** do they accept em-dashes, semicolons, parentheticals, or reject them? Honor it.
- **Hedging:** do they want claims stated flatly or softened ("may suggest")? Field- and author-specific.
- **Structural limits:** will they let you merge/split sentences, or do they want one-in-one-out edits?

## How to fold it back in

When generating the next sentence's three versions:

1. Start from the author's learned aggressiveness, not a fixed Light/Medium/Bold ladder. If they've shown they want light edits, make all three options lighter and closer together. If they want bold, push harder.
2. Apply the keep-list and kill-list automatically — don't re-propose a word they already vetoed.
3. Keep the spectrum's *purpose* even as you recenter it: the three options should still differ enough to be a real choice, just within the band the author has shown they live in.

## Preserve, don't homogenize

The failure mode to guard against: every sentence drifting toward the same clean, generic cadence until the paper loses its author. Re-read a few of their kept-original sentences periodically. Those are ground truth for their voice. If your proposals are starting to sound unlike those sentences, pull back — the author's clean original is the target, not a textbook ideal.
