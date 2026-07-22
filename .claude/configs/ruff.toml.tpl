# Python lint + format floor (matches code-style.md: "Use ruff").
# init-claude drops this as ruff.toml. Protected from agent edits by config-protection.
line-length = 100
target-version = "py311"

[lint]
# pycodestyle, pyflakes, isort, bugbear, comprehensions, pyupgrade.
select = ["E", "F", "I", "B", "C4", "UP"]
ignore = []

[lint.isort]
# stdlib → third-party → local, per code-style.md.
known-first-party = []
