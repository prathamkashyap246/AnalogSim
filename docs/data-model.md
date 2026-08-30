# Data Model

## Core Entities

### User
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    bio TEXT,
    avatar_url VARCHAR(512),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Dataset
```sql
CREATE TABLE datasets (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    category VARCHAR(100),
    version INTEGER DEFAULT 1,
    is_public BOOLEAN DEFAULT true,
    downloads_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_owner FOREIGN KEY (owner_id) REFERENCES users(id)
);
```

### Dataset Files
```sql
CREATE TABLE dataset_files (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_size BIGINT,
    mime_type VARCHAR(100),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);
```

### ML Model
```sql
CREATE TABLE models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    creator_id INTEGER NOT NULL REFERENCES users(id),
    model_type VARCHAR(100),
    version VARCHAR(50),
    model_path VARCHAR(512),
    accuracy FLOAT,
    is_public BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Analysis Result
```sql
CREATE TABLE analysis_results (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES datasets(id),
    model_id INTEGER REFERENCES models(id),
    result_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id)
);
```

## Data Format Specifications

### CSV Schema
```
circuit_id, simulation_date, temperature, frequency, impedance, phase_shift
```

### JSON Structure
```json
{
  "circuit_id": "string",
  "metadata": {
    "simulation_date": "ISO-8601",
    "temperature_range": [0, 125],
    "frequency_range": [1e6, 1e10]
  },
  "measurements": [
    {
      "frequency": number,
      "impedance": number,
      "phase_shift": number
    }
  ]
}
```

## Relationships

```
User (1) ──── (n) Dataset
User (1) ──── (n) Model
Dataset (1) ──── (n) DatasetFile
Dataset (1) ──── (n) AnalysisResult
Model (1) ──── (n) AnalysisResult
```

## Indexing Strategy

- Primary keys on all tables
- Unique indices on username, email
- Foreign key indices for joins
- Full-text search indices on descriptions
- Composite indices for common queries
