# The review prompt

Paste this after the rules are in `AGENTS.md` / `CLAUDE.md`. Point it at the system that hurts most.

```
Do a staff-engineer architecture review of <directory or service> against the rules in AGENTS.md.
Give me numbers, not adjectives. For each measure, give the count and name the worst offenders:

1. Length of the largest file, and how many route handlers still live in it versus in route files.
2. Handlers and functions over 150 lines, and over 300. List the five longest with their line counts.
3. Imports inside functions (a function-level import usually dodges a cycle: the logic is in the wrong module).
4. Direct database / model calls made from the HTTP layer instead of through an owner module.
5. HTML or other rendering built inside server-side code.
6. Identical non-trivial lines repeated four or more times. Give the top five with counts.
7. Functions that duplicate an existing utility by name.
8. Leftover files: .bak, .orig, dead scripts.
9. Domains whose rules live in more than one module. Name each domain and every file that holds part of it.

Do not change anything. Finish with: the one system to refactor first, and why, and the gates
(tests, lints, checks) that must exist before the first move.
```

Keep the output. It is your "before" table. Run the same prompt after the refactor for the "after".
