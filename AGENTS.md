# How to work in this repo

Constraints, not a checklist. When two conflict, pick the lowest future cost for this repo and say so in the commit.
The hard invariants are the strict form. Adapted from Tomas Vykruta's AGENTS.md rules (Sep 2026), with additions
from running them on a production Node service.

## Design principles (every file)

- **Separation of concerns.** Domain rules in services, HTTP in routes, schema in models. Name the one concern of
  the file you edit. Add nothing to a legacy monolith file: a new route goes in routes, a new rule in its owner.
- **Encapsulation.** Read another module's tables and caches through its functions, never directly.
- **One rule change touches one module.**
- **DRY means one home.** Grep before writing a rule, threshold, format string or schema fact; extend the home.
  Do not abstract coincidental similarity.
- **KISS / YAGNI.** Function over class. No speculative flags, hooks or layers. Boring tech.
- **Single responsibility.** If you describe it with "and", split it. Names say intent; comments say why, with a date.
- **Depend on contracts.** Domain code takes and returns plain values; it never reads the request or writes the response.
- **Fail fast, and fail closed.** Validate at the edges. On any security or authorization path an error is a refusal,
  never a pass.
- Composition over inheritance · open/closed only where change has happened twice · no `a.b.c.d` reaching ·
  optimize for deletion.

## Hard invariants

1. **One owning module per domain.** Keep a table here: domain → owner file. Consolidate a scattered domain before
   adding to it. Add a row when you confirm an owner; never add a second owner. A function-level import to dodge a
   cycle means the logic is in the wrong module.

   | Domain | Owner |
   |---|---|
   | _(fill in: e.g. "Pricing rules")_ | _(e.g. `services/pricing.js`)_ |

2. **Never duplicate logic.** On the second use: (1) move it to the owner, (2) switch the original caller, tests
   green, no behaviour change, (3) then build the new use. Grep the expression and list every copy; the move
   switches them all or the commit names each one left and why. A helper beside old copies is one more duplicate.
   Any behaviour change is its own commit. Same for schemas: one fact, one field.
3. **No business logic in HTTP or rendering.** A route parses, calls an owner, and writes the owner's result.
   Who may see or do something is decided in the owner, not in a template or a handler.
4. **A refactor never weakens a check.** Refusals, fail-closed paths, signature and key checks keep their exact
   semantics. If a refactor changes what is refused, it is not a refactor.
5. **Secrets never enter git.** A secret found in history is rotated, not just removed.

## How to work

- **Measure first.** Before refactoring a system, review it against these rules with numbers: every file, every
  copy, the longest functions. Write the baseline down; report against it afterwards.
- **Refactor first, then change.** When a change would add a second copy, grow the monolith, or cross a domain
  boundary: a behaviour-preserving refactor with tests green first, then the change, as separate commits.
- **Move code verbatim, and prove it.** Use a script, not hand edits, to move a function or handler. Verify the
  moved code is token-identical to the original (a real parser, not a regex). Anything the script cannot prove
  safe, it refuses.
- **A move includes its imports.** The body can be token-identical while the import lines the tool rebuilt are
  wrong: `const { a: b } = require(x)` rewritten as `const { b } = require(x)` is valid, declared, and undefined.
  Check that every imported name is something its module exports.
- **Gates, not promises.** A rule that matters is enforced by a test, a lint, a scan or a hook, not by a sentence
  in this file. One script runs every gate in sequence and must end green before any deploy:
  1. a boot check that loads the app the way production does, including route registration;
  2. a lint for undefined names (a syntax check and a test suite both miss a module-load ReferenceError);
  3. the full test suite, with the ORM set to THROW on a write to a field the schema lacks (in tests only);
  4. an import check: every destructured import names something the module exports;
  5. a shape test: no handler over N lines; no new domain module touches the request or response;
  6. a security scan: vulnerable dependencies, secrets in tracked files, files that must never be tracked.
  A check whose tool is missing reports SKIPPED, never pass. Never claim a check passed that was not run.
- **No exemptions.** When a gate fires on a real case, fix the case. Do not add an allowlist to silence it. A list
  of known legacy offenders may exist only if it can only shrink.
- **Deploy is self-reverting.** Pull, restart, probe and revert happen in one command on the host, one host at a
  time, the most critical host last. Pushing to git deploys nothing.
- **A probe is not a test.** After a deploy that touches a critical path, exercise that path for real, end to end,
  before calling it done. A route that answers 401 proves it is registered, not that it works.
- **Untracked files are invisible to scanners that read the index.** Stage new files before running the gates.
