# CLAUDE.md

**Project:** learning project

---

## CRITICAL: Cloud-First Development

This application runs in cloud environments (AWS/GCP/Azure).

**Never hardcode local paths:**
```
# WRONG
path = "/Users/username/projects/myapp"

# CORRECT
path = env_var("APP_ROOT", "/app")  # Use your language's equivalent
```

**Before writing code, verify:**
1. Paths work in containers (use relative paths or env vars)
2. Credentials come from environment variables
3. No local filesystem dependencies

---

## Engineering Requirements (Three Pillars)

Every production code change MUST include:

1. **Tests** — Run your test suite, aim for >80% coverage, test success AND failure paths
2. **Documentation** — Docstrings/comments for public APIs
3. **Git Commits** — Conventional format with Co-Authored-By footer

No exceptions. No shortcuts.

---

## Modular Documentation

Detailed conventions live in `.claude/rules/` and are loaded automatically:

- `@import .claude/rules/code-style.md` — coding conventions (path-filtered to `src/**`)
- `@import .claude/rules/testing.md` — testing standards (path-filtered to `tests/**`)

Add more rules files as your project grows. Use `paths:` frontmatter to scope rules to specific directories.

> **Tip:** Run `/init` to let Claude analyze your codebase and generate additional project-specific instructions.

---

## Session Continuity

Claude Code's **auto-memory** handles session context automatically. For manual tracking:

| File | Purpose | Update When |
|------|---------|-------------|
| `PROJECT_STATE.md` | System status snapshot | After feature completion |

---

## Project Structure

```
NormProject/
├── CLAUDE.md              # This file (auto-loaded)
├── CLAUDE.local.md        # Personal overrides (gitignored)
├── PROJECT_STATE.md       # System status
├── src/                   # Source code
├── tests/                 # Test files
├── docs/                  # Documentation
├── scripts/               # Utility scripts
└── .claude/
    ├── settings.json      # Shared configuration & hooks
    ├── settings.local.json # Personal overrides (gitignored)
    ├── rules/             # Modular rule files
    │   ├── code-style.md  # Coding conventions
    │   └── testing.md     # Testing standards
    └── skills/            # Custom skills
        └── commit/        # Commit workflow skill
```

---

## Available Skills & Plugins

### Local Skills (`.claude/skills/`)

- `/commit` — Git commit workflow with conventional format

### Global Plugins

| Plugin | Skills/Agents | Purpose |
|--------|---------------|---------|
| `commit-commands` | `/commit`, `/commit-push-pr`, `/clean_gone` | Git workflow automation |
| `feature-dev` | `/feature-dev` | Guided feature development |
| `pr-review-toolkit` | `/review-pr` + code-reviewer, silent-failure-hunter, type-design-analyzer | Comprehensive PR review |
| `frontend-design` | `/frontend-design` | Production-grade UI development |

> **Agent Teams** (experimental): For background multi-agent workflows, see Claude Code's agent teams feature — the successor to loop-based plugins.

---

*Last updated: 2026-02-20*
