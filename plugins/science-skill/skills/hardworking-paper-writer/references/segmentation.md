# Sentence segmentation for papers

Goal: turn the paper's prose into an ordered list of reviewable sentences with stable IDs, while leaving non-prose alone. Bad segmentation makes the whole loop frustrating, so handle the common traps below.

## What counts as a reviewable prose sentence

Review running prose: abstract, introduction, body paragraphs, discussion, conclusion, and figure/table captions (captions carry a lot of slop and are worth including).

Do **not** segment or offer rewrites for:

- Math: `$...$`, `$$...$$`, `\[...\]`, `\(...\)`, and environments like `equation`, `align`, `gather`, `multline`.
- Citations, refs, and labels: `\cite{}`, `\ref{}`, `\eqref{}`, `\label{}`, `\autoref{}` — keep them inside the sentence verbatim, never reword them.
- Structural commands: `\section{}`, `\subsection{}`, sectioning titles (a title can be polished, but flag it as a title, not a sentence).
- Comments: anything after an unescaped `%` in LaTeX.
- Tables (`tabular`), code listings (`verbatim`, `lstlisting`, `minted`), TikZ/figures.
- The preamble (everything before `\begin{document}`).
- Bibliography entries and `\bibitem`.

In Markdown, also skip fenced code blocks (```` ``` ````), inline code (`` `...` ``), YAML front matter, tables, and raw URLs/link targets. Headings can be polished but tag them as headings.

## Splitting rules

- Split on sentence-final `.`, `?`, `!` followed by whitespace and a capital/`\`/`$`.
- **Do not split** on periods inside: abbreviations (`e.g.`, `i.e.`, `et al.`, `cf.`, `vs.`, `Fig.`, `Eq.`, `Dr.`, `Sec.`), decimals (`0.05`), version numbers, ellipses (`...`), or inside math.
- A period immediately before `)` or after a closing `}` of a cite usually still ends the sentence — check context.
- Keep a trailing citation/parenthetical attached to its sentence: "...as shown previously \cite{foo}." is one sentence.
- Treat a list item or a single-line caption as one sentence even without terminal punctuation.

## Assigning IDs

Number sentences in reading order: `S001`, `S002`, … Record for each id enough to relocate it for editing — the section it lives in and the exact original text. When you apply an edit with the Edit tool, match on the full original sentence string (it is unique enough); if a sentence repeats verbatim, include a neighboring phrase to disambiguate.

## Practical approach

You don't need a perfect parser. Read the working copy, walk it section by section, and build the sentence list as you go, applying the skip rules above. When a chunk is ambiguous (a sentence wrapped around an inline equation, say), keep the equation inline and treat the surrounding words as the editable sentence — offer rewrites of the prose around the math, never the math itself.
