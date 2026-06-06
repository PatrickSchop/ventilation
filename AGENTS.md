# AGENTS.md

## Testing

The project uses `pytest` for behavior-locking tests. There is no `Makefile` and no test wrapper — run the suite directly with `python -m pytest`.

### Setup (one-time)
```
python -m pip install -r requirements-dev.txt
```

### Run all tests
```
python -m pytest
```

### Conventions for AI agents and contributors
- Touch only files listed in the phase/task you are working on. No incidental refactoring.
- Never weaken or delete a test to make it pass. If a non-xfail test is red, fix the production code.
- `xfail(strict=True)` tests are **expected to fail** until the phase that fixes their finding. Removing the marker is the act that confirms the fix.
- The phase-by-phase execution plan is at `.opencode/plans/testing-and-fixes.md`.
- After a phase's gate passes, commit only files that phase changed (`git add <explicit paths>`). Do not `git add -A`. Do not commit `config.json` credential changes. Do not push.

### Slash command
`/test` runs the full suite (see `.opencode/command/test.md`).
