from fastapi import Depends
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.simple_user import UserCreate, UserOut
from app.models.simple_user import SimpleUser
from app.database import get_async_db
from sqlalchemy import select

router = APIRouter(prefix="/user")

@router.get("/", response_model=list[UserOut])
async def get_users(db: AsyncSession = Depends(get_async_db)):
    user_list = await db.execute(select(SimpleUser).limit(100))
    return user_list.scalars().all()

@router.post("/", response_model=UserOut)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_async_db)):
    user = SimpleUser(
        name=user.name,
        money=user.money
    )
    
    db.add(user)
    
    await db.commit()
    await db.refresh(user)
    
    return user