"""
server.py
FastAPI web server for Vaya. Exposes API endpoints for chat, WhatsApp webhook, and health checks.
Handles context passing, session management, and Twilio integration.
"""
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import os
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

# Load environment variables
load_dotenv()

from agents.supervisor import create_supervisor

app = FastAPI(title="Vaya Public Transport Assistant")

# Health check endpoint for Docker and uptime monitoring
@app.get("/health")
async def health_check():
    """Simple health check for Docker/monitoring."""
    return {"status": "ok"}

# CORS configuration (open for dev; restrict in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for chat API
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    agents_used: Optional[list] = None

def get_client_ip(request: Request) -> str:
    """Extract client IP address from request headers (supports proxies)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host

# Initialize the supervisor agent (LLM router)
try:
    supervisor = create_supervisor()
except Exception as e:
    import logging
    logging.error(f"Failed to initialize supervisor: {e}")
    supervisor = None

def get_twilio_client():
    """
    Initialize and return a Twilio REST client using environment variables.
    Returns None if credentials are missing.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    if not account_sid or not auth_token:
        return None
    return Client(account_sid, auth_token)

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    From: str = Form(...),
    Body: str = Form(...),
    To: str = Form(...),
    MessageSid: str = Form(...)
):
    """
    Handle incoming WhatsApp messages from Twilio.
    Passes user message and optional location to the supervisor agent.
    Returns a Twilio MessagingResponse.
    """
    if not supervisor:
        response = MessagingResponse()
        response.message("Sorry, the assistant is currently unavailable. Please try again later.")
        return response

    try:
        # Attempt to read optional location fields Twilio may send (not always present)
        latitude = None
        longitude = None
        label = None
        try:
            latitude_val = Form("Latitude")
            longitude_val = Form("Longitude")
            label_val = Form("Label")
        except Exception:
            latitude_val = None
            longitude_val = None
            label_val = None

        def to_float(value):
            try:
                return float(value) if value not in (None, "") else None
            except Exception:
                return None

        latitude = to_float(latitude_val)
        longitude = to_float(longitude_val)
        label = label_val if label_val else None

        client_info = {"from": From, "to": To, "platform": "whatsapp"}
        if latitude is not None and longitude is not None:
            client_info["location"] = {"latitude": latitude, "longitude": longitude, "label": label}

        context = {"input": Body, "history": [], "client_info": client_info}
        agent_response = supervisor(context)
        response_text = agent_response.get("response", str(agent_response)) if isinstance(agent_response, dict) else str(agent_response)
        twilio_response = MessagingResponse()
        twilio_response.message(response_text)
        return twilio_response
    except Exception as e:
        import logging
        logging.error(f"Error processing WhatsApp message: {e}")
        response = MessagingResponse()
        response.message("Sorry, I encountered an error processing your request. Please try again.")
        return response


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest, request: Request):
    """
    Main chat API endpoint for web or mobile clients.
    Accepts a message and optional session_id, returns agent response.
    """
    if not supervisor:
        raise HTTPException(status_code=500, detail="Agent system not available")

    client_ip = get_client_ip(request)

    # Build context for supervisor agent
    context = {
        "input": chat_request.message,
        "history": [],  # Session memory could be added here
        "client_info": {"ip": client_ip, "platform": "api"}
    }

    response = supervisor(context)
    response_content = response.get("response", str(response)) if isinstance(response, dict) else str(response)

    return ChatResponse(
        response=response_content,
        session_id=chat_request.session_id or "",
        agents_used=response.get("agent_names") if isinstance(response, dict) else None
    )

if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")  # Bind to all interfaces for Docker
    port = int(os.getenv("API_PORT", "8000"))
    
    uvicorn.run(app, host=host, port=port)