from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from random import random
from contextlib import asynccontextmanager
from app.config import settings
from app.database import async_engine

from app.routers.auth import router as auth_router
from app.routers.operations import (
    appointments_router,
    audit_router,
    catalog_router,
    consultations_router,
    dashboard_router,
    invoices_router,
    medications_router,
    professionals_router,
)
from app.routers.patients import router as patients_router
from app.routers.security import router as security_router
from app.routers.simple_user import router as simple_user_router
from app.services.identity import seed_initial_data

@asynccontextmanager
async def lifespan(app: FastAPI):
    await seed_initial_data()

    yield

    await async_engine.dispose()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origins=settings.cors_origins,
    allow_credentials=True,
)

app.include_router(simple_user_router)
app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(professionals_router)
app.include_router(appointments_router)
app.include_router(consultations_router)
app.include_router(medications_router)
app.include_router(catalog_router)
app.include_router(invoices_router)
app.include_router(audit_router)
app.include_router(dashboard_router)
app.include_router(security_router)

@app.get("/")
async def random_number():
    
    
    return f"Numero aleatorio: {random()}"