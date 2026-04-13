# ResearchScope

> Open-source research intelligence for CS papers — track what matters, who drives it, what to read first, and where the research gaps are.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

---

## Features

| Feature | Description |
|---|---|
| 📄 **Paper search** | Query arXiv and Semantic Scholar from one CLI command |
| 🏆 **Read-next ranking** | Automatically prioritise papers by citations and recency |
| 🔍 **Research gap detection** | Surface under-explored topics in your saved collection |
| 💾 **Local store** | Persist papers to a lightweight JSON database |

## Installation

```bash
# Clone the repo
git clone https://github.com/kishormorol/ResearchScope.git
cd ResearchScope

# Create a virtual environment and install
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Quick Start

```bash
# Search arXiv for the latest transformer papers
researchscope search "ti:transformer" --limit 20 --save

# Search Semantic Scholar
researchscope search "large language models" --source semantic_scholar --save

# List and rank everything you've saved
researchscope list-papers

# Detect research gaps in your saved collection
researchscope gaps --top-n 10
```

## Project Layout

```
researchscope/
├── models/          # Pydantic data models (Paper, Author)
├── collectors/      # API collectors (arXiv, Semantic Scholar)
├── analysis/        # Ranking & gap-detection algorithms
├── storage/         # TinyDB-backed local persistence
└── cli.py           # Typer CLI entry point
tests/               # pytest test suite
```

## Development

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=researchscope

# Lint
ruff check researchscope tests
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT © 2026 Md Kishor Morol
