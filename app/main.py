from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from random import random
from contextlib import asynccontextmanager
from app.database import Base, async_engine

from app.routers.simple_user import router as simple_user_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await async_engine.dispose()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origins=["*"],
    allow_credentials=True,
)

app.include_router(simple_user_router)

@app.get("/")
async def random_number():
    
    
    return f"Numero aleatorio: {random()}"