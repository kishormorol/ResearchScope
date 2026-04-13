# Contributing to ResearchScope

Thank you for your interest in contributing! Here are some guidelines to help you get started.

## Getting Started

1. **Fork** the repository and clone your fork locally.
2. Create a **virtual environment** and install the development dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. Create a **feature branch** off `main`:

   ```bash
   git checkout -b feat/your-feature-name
   ```

## Code Style

- This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.
- Run `ruff check researchscope tests` before committing.
- All public functions and classes must have docstrings.
- Type hints are required for all function signatures.

## Tests

- All new features must be accompanied by tests in the `tests/` directory.
- Run the full test suite with:

  ```bash
  pytest
  ```

- Aim for at least 80 % coverage on new code.

## Pull Request Process

1. Ensure all tests pass and linting is clean.
2. Update the `README.md` if your change affects user-facing behaviour.
3. Open a pull request against `main` with a clear title and description.
4. A maintainer will review your PR and may request changes before merging.

## Reporting Issues

Please open a GitHub Issue with:
- A clear, descriptive title.
- Steps to reproduce the problem.
- Expected vs. actual behaviour.
- Your Python version and OS.

## Code of Conduct

Be respectful and constructive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/).
