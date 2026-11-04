# Contributing

Contributions should preserve the human-controlled execution boundary.

1. Open an issue describing the defect or proposed improvement.
2. Work in a feature branch and keep changes scoped.
3. Run `python scripts/check.py`, `python -m pytest -q`, and `node scripts/ui_logic_check.mjs`.
4. Add regression coverage for any API or model workflow change.
5. Never introduce a default mode that automatically sends, publishes, deploys, pays, or runs arbitrary shell commands.
6. Update README, SECURITY, ROADMAP, and CHANGELOG for changed behavior.
7. Do not commit passwords, provider keys, user data, SQLite files, or `.env`.

External adapters and high-risk actions require explicit threat modeling and human approval.
