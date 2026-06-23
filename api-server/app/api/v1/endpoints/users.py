from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cookies import set_refresh_cookie
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.investment_account import InvestmentAccount
from app.models.user import User
from app.schemas.investment_account import InvestmentAccountRead
from app.schemas.user import TokenResponse, UserCreate, UserLogin, UserRead
from app.services.refresh_token_service import issue_refresh_token
from app.services.user_service import create_user, get_user_by_email

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    if await get_user_by_email(db, payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = await create_user(db, payload.email, hash_password(payload.password))
    # No session is started here — the user signs in afterward, which mints the
    # access token + refresh cookie.
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin, response: Response, db: AsyncSession = Depends(get_db)
):
    user = await get_user_by_email(db, payload.email)
    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials" if not user else "This account uses Google sign-in",
        )
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    set_refresh_cookie(response, await issue_refresh_token(db, user.id))
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/me/accounts", response_model=list[InvestmentAccountRead])
async def get_my_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(InvestmentAccount)
        .where(InvestmentAccount.user_id == current_user.id)
        .order_by(InvestmentAccount.created_at.asc())
    )
    return rows.scalars().all()
