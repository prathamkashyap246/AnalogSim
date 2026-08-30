# Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Layer                          │
├─────────────────────────────────────────────────────────────┤
│  Web UI (Next.js)  │  Mobile (Future)  │  CLI Tools         │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                     API Gateway (FastAPI)                    │
├──────────────────────────────────────────────────────────────┤
│  - Authentication & Authorization                            │
│  - Request Validation                                         │
│  - Rate Limiting                                              │
│  - Request/Response Logging                                   │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
┌───────▼────┐ ┌───▼──────┐ ┌──▼────────┐
│  Data Svc  │ │ User Svc │ │ Model Svc │
└───────┬────┘ └───┬──────┘ └──┬────────┘
        │          │           │
┌───────▼──────────▼───────────▼────────┐
│         Persistence Layer             │
├──────────────────────────────────────┤
│  PostgreSQL │ MinIO (S3) │ Redis    │
└──────────────────────────────────────┘
        │
┌───────▼──────────────────────────────┐
│         ML Pipeline (Optional)       │
├──────────────────────────────────────┤
│  Training │ Evaluation │ Inference   │
└──────────────────────────────────────┘
```

## Component Details

### API Layer (FastAPI)
- RESTful endpoints for CRUD operations
- JWT-based authentication
- Request validation with Pydantic
- Automatic OpenAPI/Swagger documentation
- Dependency injection for services

### Database Layer
- **PostgreSQL**: Relational data (users, datasets, metadata)
- **MinIO**: Object storage for large simulation files
- **Redis**: Caching and session management

### Service Layer
- **Data Service**: Dataset management, versioning, lineage
- **User Service**: Authentication, authorization, profiles
- **Model Service**: ML model management and execution
- **Analysis Service**: Data analysis and visualization

### Frontend (Next.js)
- Server-side rendering for SEO
- Client-side data fetching with SWR
- Authentication flow with JWT
- Responsive design with Tailwind CSS

## Database Schema

### Core Tables
- `users`: User profiles and authentication
- `datasets`: Dataset metadata and versioning
- `dataset_files`: Associated files for datasets
- `models`: ML model registry
- `analysis_results`: Cached analysis outputs
- `audit_log`: Change tracking

See `docs/data-model.md` for detailed schema.

## Deployment Architecture

### Development
- Docker Compose for local development
- PostgreSQL in container
- MinIO for local S3-compatible storage

### Production (Future)
- Kubernetes cluster
- Managed PostgreSQL (AWS RDS/GCP Cloud SQL)
- S3 or equivalent object storage
- Container registry for images
- Load balancing and auto-scaling
