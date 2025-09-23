from fastapi import FastAPI, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.chat_repository import ChatCrud
from app.core.config import settings
from app.curriculum.service.retake_service import RetakeService
from app.database.connection import init_db, close_db, get_db
from app.chat.websocket_handler import WebSocketHandler

from app.user.user_models import User
from app.curriculum.curriculum_models import Curriculum, CurriLecture, Records

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()

app = FastAPI(
    title="Curriculum Design Chatbot",
    description="AI-powered curriculum design and recommendation system",
    version="1.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Curriculum Design Chatbot API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "curriculum-chatbot"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    handler = WebSocketHandler(db)
    await handler.handle_websocket(websocket)

@app.get("/chat/history")
async def get_history(userId: int, db: AsyncSession = Depends(get_db)):
    crud = ChatCrud(db)
    logs = await crud.get_chat_history_by_user(userId)
    return {
        "chatHistory": [
            {
                "sender": "user" if log.chat_type == "U" else "assistant",
                "content": log.message,
                "timestamp": log.timestamp
            }
            for log in logs
        ]
    }

@app.get("/chat/history/session")
async def get_history_by_session(sessionId: int, db: AsyncSession = Depends(get_db)):
    crud = ChatCrud(db)
    logs = await crud.get_chat_history_by_session(sessionId)
    return {
        "chatHistory": [
            {
                "sender": "user" if log.chat_type == "U" else "assistant",
                "content": log.message,
                "timestamp": log.timestamp.isoformat()
            }
            for log in logs
        ]
    }


@app.get("/retake/eligible/{user_id}")
async def get_retake_eligible_courses(user_id: int, db: AsyncSession = Depends(get_db)):
    """사용자의 재수강 가능 과목 목록 조회"""
    try:
        retake_service = RetakeService(db)
        retake_candidates = await retake_service.get_retake_eligible_courses(user_id)

        return {
            "success": True,
            "message": "재수강 가능 과목 조회 성공",
            "data": {
                "user_id": user_id,
                "retake_candidates": retake_candidates,
                "total_count": len(retake_candidates)
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"재수강 가능 과목 조회 실패: {str(e)}",
            "data": None
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)