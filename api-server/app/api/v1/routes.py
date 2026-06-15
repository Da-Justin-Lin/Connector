from fastapi import APIRouter

from app.api.v1.endpoints import auth, snaptrade, users

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(snaptrade.router, prefix="/snaptrade", tags=["SnapTrade"])
