import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def register_cors(app: FastAPI) -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    raw = os.environ.get("ALLOWED_CORS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
