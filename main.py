import os
from dotenv import load_dotenv
load_dotenv()  # Must be called before any config/settings import

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from config.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="Adaptive Onboarding Agent",
    description="Self-learning onboarding for a health ecommerce app powered by Gemini + LangGraph",
    version="1.0.0",
)

# Allow the frontend (served on the same origin) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve the frontend HTML at the root URL
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.app_port, reload=True)
