---
name: slop-score
description: Score a codebase for slop, 0 (clean) to 100 (slop), against the deslop rules (AGENTS.md), and summarise every broken rule with its worst offenders. Works on JavaScript/TypeScript, Go and Python; other languages get the file-level measures. Use when asked for a slop score, a deslop review, a before/after number for a refactor, or "how sloppy is this repo".
---

# Slop score

Produces one number and a summary of every broken rule. Read-only: change nothing in the repo being scored.

The rules are the ones in `AGENTS.md` of https://github.com/minitru/deslop-rules (Tomas Vykruta's rules plus the
additions from running them on a production service). If the repo being scored has its own `AGENTS.md` or
`CLAUDE.md`, read it too: its owner table tells you which module owns which domain.

## 1. Measure

`measure.py` sits next to this file. Run it on the directory the user named (default: the repo root):

```bash
python3 <this skill's directory>/measure.py <directory>
```

Python 3, no dependencies, no network. Add `--json` for machine-readable output. It prints the score, then every
measure with its points, its count and the worst offenders as `file:line`.

**The number is the script's and only the script's.** Do not adjust it, round it, or average it with your own
opinion: the same tree must always give the same score, so a "before" can be compared with an "after". There is no
ignore list and no flag that switches a measure off. If the user asks to exclude something, say that the rule is
"fix the case, not the scan" and score a subdirectory instead.

## 2. Check the offenders

The script counts with line and indentation heuristics, not a parser. Open the worst offenders it names (the top
two or three per rule that scored points) and confirm each is what the script says it is. Where one is not
(a "function name defined in two files" that is two different functions; a "secret" that is a public web key),
say so in the summary as **not confirmed**, and leave the number alone.

Never print the value of anything the secrets measure found. File and line only.

## 3. Read for what cannot be counted

These rules have no measure. Read enough of the code to answer each, and report findings separately, labelled
"found by reading" (they do not change the score):

- **One owner per domain.** Which domains have rules in more than one module? Name the domain and every file.
- **A refactor never weakens a check.** On authorization, signature and key paths: does any error path end in a
  pass? Look first at the swallowed errors the script listed.
- **Who may see or do something is decided in the owner**, not in a handler or a template.
- **KISS / YAGNI.** Flags, hooks, layers or classes that nothing uses.
- **Gates.** The script only sees that tests, a lint and a gate script exist. Does one command run all of them, and
  does a missing tool report SKIPPED instead of pass?

## 4. Report

Keep it short and plain. In this order:

1. `Slop score: N / 100 (grade)`, the directory, code lines, languages.
2. A table of the rules that scored points, worst first: rule · what was found (the count) · points of maximum ·
   the one or two worst offenders as clickable `file:line`.
3. Offenders you opened that were not confirmed.
4. Found by reading: each with file references.
5. Rules that came out clean, in one line.
6. The one thing to fix first, and the gate that should exist before the first move.

If the user asked for a before/after, run the script on both trees (a `git archive <commit> | tar -x -C <scratch dir>`
copy works for the "before"; the script falls back to walking the directory when it is not a git repository) and
give the two tables side by side.

## What the script measures

| Points | Rule | Measure |
|---|---|---|
| 14 | No business logic in HTTP | database calls in files that register routes or handle requests |
| 14 | Single responsibility | functions and handlers over 150 lines (over 300 counts double) |
| 14 | Never duplicate logic | six-line blocks that exist twice; identical lines repeated 4+ times |
| 12 | Separation of concerns | largest file; share of code in files over 1,000 lines |
| 8 | Secrets never enter git | key blocks, provider tokens, hard-coded credentials, `.env` and key files |
| 6 | One owner per domain | imports inside functions (not applicable to Go) |
| 6 | No logic in rendering | HTML built inside server-side code |
| 6 | Never duplicate logic | the same top-level function name defined in several files |
| 6 | Fail fast, fail closed | empty catch, `except: pass`, dropped Go errors |
| 6 | Gates, not promises | tests, a lint, a CI or gate script present |
| 4 | Optimize for deletion | leftover `.bak`, `.orig`, `copy` files |
| 4 | No exemptions | lint suppressions, skipped tests |

A measure that does not apply (no HTTP layer, a Go-only repo for inner imports) is left out and the score is taken
over the rest. Tests, vendored and generated code are not scored, except for suppressions and skipped tests.
Grades: 0–10 A, 11–25 B, 26–45 C, 46–65 D, above 65 F.
