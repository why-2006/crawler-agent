from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.login import router as login_router
from app.api.tasks import router as tasks_router, _run_crawl
from app.api.websocket import router as ws_router
from app.config import settings
from app.scheduler import TaskScheduler
from app.storage.database import init_db

scheduler = TaskScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.set_run_crawl(_run_crawl)
    await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(
    title="Crawler Agent",
    description="基于 LangChain + 大模型的通用爬虫 Agent",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(ws_router)
app.include_router(login_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
