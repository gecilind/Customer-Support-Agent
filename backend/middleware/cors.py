from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI


def register_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
