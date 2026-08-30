# Contributing to Analog Data Commons

Thank you for your interest in contributing! This document provides guidelines and instructions.

## Code of Conduct

Please be respectful and constructive in all interactions.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/AnalogSim.git`
3. Create a feature branch: `git checkout -b feature/your-feature`
4. Make changes and commit: `git commit -am 'Add your feature'`
5. Push to your fork: `git push origin feature/your-feature`
6. Create a Pull Request

## Development Setup

```bash
# Install dependencies
cp .env.example .env
docker-compose up -d

# For API development
cd apps/api
pip install -r requirements.txt
pytest tests/

# For Web development
cd apps/web
npm install
npm run dev
```

## Coding Standards

- **Python**: Follow PEP 8 with Black formatter
- **JavaScript/TypeScript**: Follow ESLint config
- **Database**: Use migrations for schema changes
- **Documentation**: Keep docs up-to-date with code changes

## Testing

- Write tests for new features
- Ensure all tests pass: `pytest` or `npm test`
- Aim for >80% code coverage

## Pull Request Process

1. Update documentation as needed
2. Add tests for new functionality
3. Ensure all CI checks pass
4. Request review from maintainers
5. Address review feedback
6. Squash commits if requested

## Reporting Issues

- Check if issue already exists
- Provide detailed reproduction steps
- Include environment information
- Attach relevant logs or screenshots

## Questions?

Feel free to open an issue or start a discussion!
