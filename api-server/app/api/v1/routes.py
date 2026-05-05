from fastapi import APIRouter

from app.api.v1.endpoints import plaid, users

router = APIRouter()
router.include_router(plaid.router, prefix="/plaid", tags=["Plaid"])
router.include_router(users.router, prefix="/users", tags=["Users"])
