# Analog Data Commons

A comprehensive platform for aggregating, managing, and analyzing analog circuit simulations.

## Vision

Build a collaborative ecosystem where researchers and engineers can:
- Share analog circuit simulation datasets
- Collaborate on ML models for circuit analysis
- Access standardized APIs for data and analysis
- Contribute to a growing knowledge base

## Quick Start

```bash
# Clone repository
git clone https://github.com/prathamkashyap246/AnalogSim.git
cd AnalogSim

# Set up environment
cp .env.example .env

# Start with Docker
docker-compose up -d

# Access services
- Web: http://localhost:3000
- API: http://localhost:8000
- MinIO: http://localhost:9001
```

## Documentation

- [Vision & Goals](docs/vision.md)
- [Architecture](docs/architecture.md)
- [Data Model](docs/data-model.md)
- [API Specification](docs/api-spec.md)
- [Roadmap](docs/roadmap.md)

## Project Structure

```
analog-data-commons/
├─ apps/         # Frontend & Backend applications
├─ ml/           # Machine learning pipelines and models
├─ data/         # Sample datasets and schemas
├─ db/           # Database migrations and initialization
├─ infra/        # Infrastructure configuration (Docker, K8s)
├─ docs/         # Documentation
└─ .github/      # CI/CD workflows and templates
```

## Tech Stack

### Backend
- **Framework**: FastAPI
- **Database**: PostgreSQL
- **Storage**: MinIO (S3-compatible)
- **Task Queue**: Celery (optional)

### Frontend
- **Framework**: Next.js
- **UI**: React + TypeScript
- **Styling**: Tailwind CSS

### ML
- **Frameworks**: PyTorch, scikit-learn, XGBoost
- **Data**: pandas, numpy
- **Visualization**: matplotlib, plotly

## Development

```bash
# Install dependencies
make setup

# Run tests
make test

# Start development servers
make dev

# Code quality checks
make lint
make format
```

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting PRs.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contact

For questions or feedback, open an issue or contact the maintainers.
