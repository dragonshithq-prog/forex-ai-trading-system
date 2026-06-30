# Contributing to Forex AI Trading System

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## Development Process

### 1. Fork & Branch

```bash
git clone https://github.com/your-username/forex-trading-system.git
cd forex-trading-system
git checkout -b feature/your-feature-name
```

### 2. Setup Development Environment

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd frontend
npm install

# Start infrastructure
docker-compose -f docker/docker-compose.yml up -d
```

### 3. Code Standards

#### Python (Backend)
- **Formatter**: Black (line length: 100)
- **Linter**: Ruff
- **Type Checker**: Mypy
- **Style**: PEP 8 with 4-space indentation

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ --fix

# Type check
mypy src/
```

#### TypeScript (Frontend)
- **Formatter**: Prettier
- **Linter**: ESLint
- **Style**: Airbnb TypeScript Style Guide

```bash
# Format code
npm run format

# Lint code
npm run lint
```

### 4. Commit Messages

Use Conventional Commits:

```
feat: add new AI agent for sentiment analysis
fix: resolve broker connection timeout
docs: update API documentation
style: format code with black
refactor: extract risk calculation logic
test: add unit tests for strategy engine
chore: update dependencies
```

### 5. Pull Request Process

1. Update documentation if needed
2. Add tests for new functionality
3. Ensure all tests pass:
   ```bash
   cd backend && pytest
   cd frontend && npm test
   ```
4. Ensure code passes linting and type checks
5. Create PR with clear description
6. Request review from maintainers

### 6. Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Code refactoring
- `test/description` - Test additions

## Architecture Guidelines

### Clean Architecture

Follow the dependency rule:
- **Domain** (innermost): Entities, Value Objects, Domain Events
- **Application**: Use Cases, Service Interfaces
- **Infrastructure**: Database, External APIs, Message Brokers
- **Presentation**: API Controllers, UI Components

Dependencies point INWARD toward the Domain layer.

### Domain-Driven Design

- Use ubiquitous language in code
- Keep bounded contexts clear
- Aggregate roots enforce invariants
- Domain events for cross-context communication

### Testing Strategy

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **E2E Tests**: Test complete user flows
- **Security Tests**: Test for vulnerabilities

Target: >80% code coverage

## Security Guidelines

- Never commit secrets or API keys
- Use environment variables for configuration
- Validate all user inputs
- Follow OWASP security guidelines
- Run security scans before merging

## Questions?

Open an issue or reach out to the maintainers.
