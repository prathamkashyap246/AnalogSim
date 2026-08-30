"""Authentication routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/register")
def register(request: RegisterRequest):
    """Register a new user."""
    # TODO: Implement user registration
    return {"id": 1, "username": request.username, "email": request.email, "token": "mock_token"}

@router.post("/login")
def login(request: LoginRequest):
    """User login."""
    # TODO: Implement user login
    return {"token": "mock_token", "expires_in": 3600}
