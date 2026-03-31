# Contributing

## Principles

- Keep changes small and production-oriented
- Prefer environment-driven configuration over hardcoded edits
- Do not add new dependencies without a clear need
- Preserve the existing service shape unless the change requires it

## Workflow

1. Open an issue or describe the problem clearly.
2. Keep implementation scoped to the reported problem.
3. Add or update focused tests when behavior changes.
4. Run `pytest` before opening a pull request.
5. Sanitize all examples, logs, and screenshots.

## Pull Request Checklist

- [ ] Tests pass
- [ ] No secrets or live identifiers are included
- [ ] Docs are updated if behavior or setup changed
- [ ] New configuration is documented
