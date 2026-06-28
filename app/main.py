import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
import uvicorn

from app.configuration.database import init_pool, close_pool
from app.routers.dashboard_router import router as dashboard_router
from app.routers.alert_router import router as alert_router
from app.routers.ingest import router as ingest_router
from app.routers.ws_router import router as ws_router

app = FastAPI(
    title="RailOptic API",
    description="RailOptic API — detection ingestion, alerts, dashboard and websocket updates.",
    version="0.1.0",
    docs_url="/swagger",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = " -> ".join([str(l) for l in err.get("loc", [])])
        msg = err.get("msg", "Invalid input")
        errors.append(f"{loc}: {msg}")

    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation Error", "errors": errors},
    )

@app.get("/")
async def root():
    return {"message": "Welcome to the RailOptic Smart Railway Obstacle Detection API"}

app.include_router(dashboard_router, tags=["Dashboard"])
app.include_router(alert_router, tags=["Alerts"])
app.include_router(ingest_router, prefix="/ingest", tags=["Ingest"])
app.include_router(ws_router, tags=["WebSocket"])

@app.on_event("startup")
async def on_startup():
    await init_pool()

@app.on_event("shutdown")
async def shutdown_event():
    await close_pool()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
