from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the agent supervisor
from agents.supervisor import create_supervisor


app = FastAPI(title="Kura Lab Public Transport Assistant")

# Health check endpoint for Docker
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Chat models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    agents_used: Optional[list] = None

# Utility to get client IP
def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host

# Initialize the supervisor
try:
    supervisor = create_supervisor()
except Exception as e:
    import logging
    logging.error(f"Failed to initialize supervisor: {e}")
    supervisor = None

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest, request: Request):
    if not supervisor:
        raise HTTPException(status_code=500, detail="Agent system not available")
    client_ip = get_client_ip(request)
    response = supervisor.invoke({"input": chat_request.message})
    response_content = response.get("response", str(response)) if isinstance(response, dict) else str(response)
    return ChatResponse(
        response=response_content,
        session_id=chat_request.session_id or "",
        agents_used=response.get("agents_used") if isinstance(response, dict) else None
    )

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")  # Bind to all interfaces for Docker
    port = int(os.getenv("API_PORT", "8000"))
    
    uvicorn.run(app, host=host, port=port)