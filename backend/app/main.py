import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.api_core.exceptions import GoogleAPICallError

from app.config import Settings
from app.routers import chat, conversations, data
from app.services.chat import ChatService
from app.store import FirestoreStore, LocalStore


def create_app(settings=None, database=None, chat_service=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        if not settings.demo and not settings.gemini_key and chat_service is None:
            raise RuntimeError("GEMINI_API_KEY를 설정하세요. 키 없는 로컬 확인은 DEMO_MODE=true로 실행하세요.")
        app.state.settings = settings
        app.state.store = database or (LocalStore(settings.local_path) if settings.demo else FirestoreStore(settings))
        app.state.chat = chat_service or ChatService(settings)
        yield
        if getattr(app.state.chat, "client", None):
            app.state.chat.client.close()
        if hasattr(app.state.store, "close"):
            app.state.store.close()

    app = FastAPI(title="Bikewise API", version="1.0.0", lifespan=lifespan,
                  description="공유자전거 시계열 데이터 CRUD, 요약 기반 AI 채팅, 대화 기록 API. "
                  "대화 API는 X-Session-ID 헤더(32자 이상)가 필요합니다. 데이터는 공용입니다.")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.origins),
                       allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type", "X-Session-ID"])

    @app.exception_handler(GoogleAPICallError)
    async def firestore_error(request: Request, exc):
        logging.getLogger("bikewise").error("Firestore request failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "데이터베이스 연결에 실패했습니다. 잠시 후 다시 시도하세요."})

    @app.get("/health", tags=["운영"])
    def health(request: Request):
        return {"status": "ok", "demo": settings.demo,
                "database": "local-json" if settings.demo else "firestore",
                "ai": "demo-template" if settings.demo else settings.model}

    app.include_router(data.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)
    return app


app = create_app()
