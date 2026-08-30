# Database migrations directory

This directory contains Alembic migrations for database schema updates.

To create a new migration:
```bash
alembic revision --autogenerate -m "Description of changes"
```

To apply migrations:
```bash
alembic upgrade head
```
