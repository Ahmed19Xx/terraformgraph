# Contributing to terraformgraph

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/ferdinandobons/terraformgraph.git`
3. Create a virtual environment: `python -m venv venv && source venv/bin/activate`
4. Install dev dependencies: `pip install -e ".[dev]"`
5. Create a branch: `git checkout -b feature/your-feature`

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Style

We use `black` for formatting and `ruff` for linting:

```bash
black terraformgraph/
ruff check terraformgraph/
```

### Adding New Resource Types

1. Add the resource mapping to `config/aggregation_rules.yaml`
2. Add icon mapping to `terraformgraph/icons.py` in `TERRAFORM_TO_ICON`
3. Add any new connections to `config/logical_connections.yaml`
4. Add tests for the new resource type

## Pull Request Process

1. Ensure all tests pass
2. Update documentation if needed
3. Add a clear description of changes
4. Reference any related issues

## Code of Conduct

Be respectful and constructive. We're all here to build something useful together.

## Questions?

Open an issue with your question and we'll help out!
