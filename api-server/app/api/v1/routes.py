from fastapi import APIRouter

from app.api.v1.endpoints import auth, deposits, market, reports, snaptrade, users

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(snaptrade.router, prefix="/snaptrade", tags=["SnapTrade"])
router.include_router(market.router, prefix="/market", tags=["Market Data"])
router.include_router(deposits.router, prefix="/deposits", tags=["Deposits"])
router.include_router(reports.router, prefix="/reports", tags=["Reports"])
