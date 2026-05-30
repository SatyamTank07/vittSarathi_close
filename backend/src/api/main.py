from dotenv import load_dotenv
load_dotenv()  # Load variables from .env file if it exists

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.database.connection import engine
from src.core.database import models
from src.api.routes import stock_routes, report_routes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="vittSarathi API — Multi-Agent Stock Analysis")

# Allow connections from the frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "status": "running",
        "message": "vittSarathi backend is active!",
        "version": "3.0 — Modular Agent Architecture",
    }

app.include_router(stock_routes.router)
app.include_router(report_routes.router)
