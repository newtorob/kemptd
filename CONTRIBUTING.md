# Contributing to kemptd

Thanks for your interest! kemptd aims for a small, sharp codebase with a pure,
well-tested core.

## Development setup

```console
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Before you push

The CI gate is the same as local:

```console
ruff format --check .
ruff check .
mypy
pytest
```

## Ground rules

- **Keep the core pure.** `parse`, `matching`, and planning must not do IO or
  network calls. Anything with side effects goes behind a provider interface or
  the apply layer so the core stays deterministic and testable.
- **Everything is typed.** `mypy --strict` must pass; no untyped defs.
- **Tests travel with code.** New parsing/matching behavior needs table-driven
  cases (ideally seeded from real-world names) plus a property test where it fits.
- **Safety is non-negotiable.** The apply layer never deletes and must stay
  reversible via the journal.

## Commits

We use [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`). Keep subjects
imperative and under ~72 chars.

## License

By contributing you agree your work is licensed under GPL-3.0-or-later.
