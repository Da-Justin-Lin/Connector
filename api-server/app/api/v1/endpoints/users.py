from fastapi import APIRouter, HTTPException

from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserRead

router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=201)
async def register(payload: UserCreate):
    """Register a new user. (DB layer not yet wired — implement with get_db session.)"""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    """Authenticate a user and return a JWT access token."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/me", response_model=UserRead)
async def get_me():
    """Return the current authenticated user. Requires JWT bearer token."""
    raise HTTPException(status_code=501, detail="Not implemented")
