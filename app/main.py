from fastapi import FastAPI, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.chat_repository import ChatCrud
from app.core.config import settings
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)