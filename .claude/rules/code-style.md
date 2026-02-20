---
paths:
  - "src/**"
---

# Code Style

<!-- Customize these conventions for your language and project -->

- Use consistent naming: `snake_case` for functions/variables, `PascalCase` for classes/types
- Keep functions focused — one responsibility per function
- Use environment variables for configuration, never hardcode secrets
- Prefer explicit over implicit — avoid magic numbers, use named constants
- Use parameterized queries for database operations (never string interpolation)
