# deslop-rules

Coding rules from the '90s, written down for AI coding agents, plus the gates that make them hold.

AI agents write code at the speed you can ask for it. A year of that gave me a 14,294-line `server.js`. These rules,
an honest measurement, and a day of agent-driven refactoring took it to 1,023 lines, with every route in its own
file and every rule in one place. The bugs it found along the way were the bonus.

The rules are adapted from [Tomas Vykruta's AGENTS.md thread](https://x.com/tvykruta/status/2105302045573959697)
(Sep 2026). The additions come from running them on a production Node service and from the things that went wrong.

## What's here

| File | What it is |
|---|---|
| [`AGENTS.md`](AGENTS.md) | The rules. Drop it in your repo as `AGENTS.md` or `CLAUDE.md` |
| [`prompts/review.md`](prompts/review.md) | The prompt that measures your code against the rules, with numbers |
| [`gates/`](gates/) | Example gates for a Node/Express service: boot check, import check, handler-shape test, strict schemas, and the script that runs them all |

## How to use it

1. **Paste the rules in.** Copy `AGENTS.md` into your repo. Ask your agent to adapt the wording to your stack, and
   fill in the owner table for the system that hurts most.
2. **Measure.** Run the review prompt. You get a table of counts: the longest file, handlers over 150 lines,
   duplicated lines, imports inside functions. That table is your slop score. Keep it.
3. **Build the gates before the first refactor.** The rules don't hold without them. An agent will tell you a move
   was safe; a gate will show you.
4. **Refactor first, then change.** Small moves, verbatim, by script, each one behind green gates.
5. **Measure again.**

## What it did for one repo

One service, about 95,000 lines of JavaScript, measured before and after roughly a day of refactoring by an agent
working under these rules:

| Measure | Before | After |
|---|---|---|
| Largest file (`server.js`) | 14,294 lines | 1,023 |
| Route handlers in the monolith vs in route files | 139 vs 409 | 6 vs 562 |
| Handlers over 150 lines / over 300 | 12 / 6 | 0 / 0 |
| Imports inside functions | 991 | 431 |
| Database calls made directly from the HTTP layer | 890 | 610 |
| Copy-pasted `catch → 500` one-liners | 80 | 4 |
| Functions duplicating a utility by name | 5 | 0 |

The same pass found fields that had been written for months and never stored, a privacy bug in account deletion,
and credentials that outlived the thing they belonged to. None of those were what it was looking for.

## Lessons the rules didn't have at the start

Each of these is now in `AGENTS.md`, and each was learned by getting it wrong.

- **A syntax check and a test suite both miss a crash at load.** An import below its first use boots fine in tests
  and crash-loops in production. Hence the boot check.
- **Code inside your `listen()` callback is invisible to everything.** Routes defined there don't exist until
  startup finishes, and no boot check, lint or line-based tool sees them.
- **"Moved verbatim" covers the body, not the imports.** A tool rebuilt `const { a: b } = require(x)` as
  `const { b } = require(x)`. It is valid, declared, and undefined. Every gate passed. Hence the import check.
- **A probe is not a test.** A route that answers 401 is registered. Whether it works is a different question, and
  the answer came from a person trying it.
- **Strict schemas in tests.** An ORM that silently drops unknown fields hides writes that never land.
- **No exemptions.** The gate that fires on an awkward case is usually right. Fix the case.

## Notes

- The gates are examples for Node, Express and Mongoose. The shape matters more than the code: one script, every
  gate in sequence, the first red one stops you, and a missing tool says SKIPPED, never pass.
- Size limits are for the HTTP layer. A 150-line limit on handlers pushed logic into named owners, which is the
  point; it is not a limit on every function.
- Your agent will want to refactor and change behaviour in one commit. Don't let it.

## Credit and licence

Rules adapted from Tomas Vykruta's thread, linked above. Additions and gates by Sean MacGuire, written with Claude.
MIT licence for the code in `gates/`; use the rules however you like.
