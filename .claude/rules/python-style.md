---
description: Python code formatting and style conventions for this project
paths:
  - "**/*.py"
---

# Python Style Rules

## Formatting Standards
- Follow PEP 8 style guidelines strictly
- Use 4 spaces for indentation (no tabs)
- Line length maximum of 88 characters (Black/Ruff formatter standard)
- Use double quotes for strings consistently
- Add proper spacing around operators and after commas

## Code Organization
- Import statements at the top, grouped: standard library, third-party, local imports
- Separate import groups with blank lines
- Two blank lines before top-level class and function definitions
- One blank line before method definitions within classes

## Naming Conventions
- Functions and variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_underscore_prefix`
- Type hints: Required for all function signatures
- Prefer `dict[str, Any]` over `Dict[str, Any]` (modern Python 3.11+ generics)

## Documentation & Comments
- Use Sphinx-style docstrings with `:param`, `:return`, and `:raises` sections
- Add inline comments for complex logic
- Include type hints for all function parameters and return values

## Error Handling
- Wrap external API calls in try-except blocks
- Raise `McpError(ErrorData(...))` for MCP tool failures with proper error codes
- Include `request_id` in all log messages
- Use structured logging with request context

## Logging Standards
- Include `request_id` from context in log messages
- Log levels: INFO for operations, ERROR for failures, DEBUG for troubleshooting
- Format: `"{request_id}: {message}"`
