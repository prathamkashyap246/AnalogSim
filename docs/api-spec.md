# API Specification

## Base URL
- Development: `http://localhost:8000/api/v1`
- Production: `https://api.analog-data-commons.io/api/v1`

## Authentication

All endpoints (except `/auth/*`) require Bearer token in header:
```
Authorization: Bearer <jwt_token>
```

### POST /auth/register
Register a new user.

**Request**
```json
{
  "username": "string",
  "email": "string",
  "password": "string",
  "full_name": "string"
}
```

**Response (201)**
```json
{
  "id": "integer",
  "username": "string",
  "email": "string",
  "token": "string"
}
```

### POST /auth/login
User login.

**Request**
```json
{
  "email": "string",
  "password": "string"
}
```

**Response (200)**
```json
{
  "token": "string",
  "expires_in": "integer (seconds)"
}
```

## Datasets

### GET /datasets
List all public datasets with pagination.

**Query Parameters**
- `skip`: integer (default: 0)
- `limit`: integer (default: 20, max: 100)
- `category`: string (optional)
- `search`: string (optional, full-text search)

**Response (200)**
```json
{
  "items": [
    {
      "id": "integer",
      "title": "string",
      "description": "string",
      "owner": {"id": "integer", "username": "string"},
      "created_at": "ISO-8601",
      "downloads_count": "integer"
    }
  ],
  "total": "integer"
}
```

### POST /datasets
Create a new dataset.

**Request** (multipart/form-data)
- `title`: string (required)
- `description`: string
- `category`: string
- `files`: file[] (required)

**Response (201)**
```json
{
  "id": "integer",
  "title": "string",
  "created_at": "ISO-8601"
}
```

### GET /datasets/{id}
Get dataset details.

**Response (200)**
```json
{
  "id": "integer",
  "title": "string",
  "description": "string",
  "owner": {...},
  "files": [
    {
      "id": "integer",
      "file_name": "string",
      "file_size": "integer",
      "uploaded_at": "ISO-8601"
    }
  ],
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

### PUT /datasets/{id}
Update dataset (owner only).

**Response (200)** - Updated dataset object

### DELETE /datasets/{id}
Delete dataset (owner only).

**Response (204)** - No content

## Models

### GET /models
List available ML models.

**Query Parameters**
- `skip`: integer (default: 0)
- `limit`: integer (default: 20)

**Response (200)** - List of model objects

### POST /models/predict
Run inference on a dataset.

**Request**
```json
{
  "model_id": "integer",
  "dataset_id": "integer"
}
```

**Response (200)**
```json
{
  "results": [...],
  "accuracy": "float",
  "execution_time": "float (seconds)"
}
```

## Error Responses

### 400 Bad Request
```json
{
  "detail": "string",
  "errors": [{"field": "string", "message": "string"}]
}
```

### 401 Unauthorized
```json
{"detail": "Invalid or missing authentication token"}
```

### 403 Forbidden
```json
{"detail": "Insufficient permissions"}
```

### 404 Not Found
```json
{"detail": "Resource not found"}
```

### 500 Internal Server Error
```json
{"detail": "Internal server error"}
```
