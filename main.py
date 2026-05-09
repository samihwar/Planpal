import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.routes import router


load_dotenv()

app = FastAPI(title="PlanPal", version="0.1.0")
app.include_router(router)

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
