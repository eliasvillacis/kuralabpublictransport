<p align="center">
  <img src="https://img.shields.io/badge/Vaya-1.0-222222?style=for-the-badge" alt="Vaya" />
</p>

<h1 align="center">🗺️ Vaya</h1>

<p align="center"><em>Conversational AI for city navigation, weather, transit, and more.</em></p>

---

## 📖 Overview

Vaya isn’t trying to replace full-featured navigation apps like Google Maps or Waze. Instead, it’s a lightweight, conversational companion built for pedestrians and public transit riders. Large apps already cover turn-by-turn driving, charging stations, and detailed transit feeds — but they can feel heavy, drain battery with constant GPS, and bury updates inside menus.

Vaya keeps things simple: ask in plain language, and get fast weather or transit checks, disruption alerts, or directions that live right in your chat. No constant tracking — just lightweight, on-demand insights with real-time updates when they matter. Directions stay in the conversation, making them easier to reference without reopening a map. The goal is confidence and clarity in your journey, without the overhead of a full navigation stack.


---

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose (recommended), or Python 3.8+
- Google Cloud API key (Maps, Places, Routes, Geolocation, Weather, etc.)
- Google Gemini API key (LLM)
- Transitland API key (public transit)
- Twilio account (WhatsApp integration, optional)
- Render.com account (cloud deployment, optional)

> The codebase is set up for Google Maps, Gemini, Transitland, Twilio, and Render. You can substitute other providers with small code changes — see [ARCHITECTURE.md](ARCHITECTURE.md) for integration patterns.

---

### 1) Clone & Set Up
    git clone <repo-url>
    cd kuralabpublictransport
    cp .env.example .env   # then edit with your API keys

---

### 2) Local Development

Create and activate a virtual environment (recommended):  
    python -m venv .venv
    source .venv/bin/activate   # Linux/macOS
    .venv\Scripts\activate      # Windows
    pip install -r requirements.txt

Run in **CLI mode** for quick testing:  
    python main.py

Or run the **API server** (FastAPI, useful for WhatsApp/other webhook testing):  
    python server.py

---

### 3) Deployment with Docker

For production or team testing, run everything in containers:  
    docker-compose up --build

This builds the image, installs dependencies, and starts the FastAPI server (`server.py`) inside Docker. CLI mode is mainly for local dev, while Docker is the recommended way to deploy. Vaya is set up with Render, but you can use whatever you like. 

---

### 4) Deploy on Render

Option A: One-click via `render.yaml` (recommended)

1. Push this repo to GitHub.
2. In Render, create a new Web Service from your repo. Render will detect `render.yaml`.
3. Use the Free plan to start; it will build the Dockerfile and run uvicorn.
4. Health check: Render uses `GET /health`.
5. Set environment variables in the Render dashboard:
    - Required in production: `GOOGLE_GENAI_API_KEY`, `GOOGLE_CLOUD_API_KEY`
    - Optional: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`, `TRANSITLAND_API_KEY`
    - For offline testing, you can set `TEST_MODE=1` (no external calls, deterministic stubs)

Notes:
- The Dockerfile binds to `PORT` if provided (Render sets it automatically).
- Healthcheck in the container also uses `${PORT}`.
- `server.py` allows startup in TEST_MODE without LLM keys; in production it uses real keys.


---

## ✨ Features

- Conversational city navigation (weather, transit, traffic, maps)  
- Multi-agent architecture (LLM supervisor + specialist agents)  
- Runs as CLI or FastAPI server; WhatsApp via Twilio webhook  
- Modular, extensible, and Docker-ready  

---

## 💻 Usage

### CLI
Run `python main.py` and ask something like:  
> “What’s the weather at Union Square at 1 pm?”

### API Server (FastAPI)
Run `python server.py` and use:  
- `POST /chat` — body: `{ "message": "..." }`  
- `POST /whatsapp` — Twilio webhook for WhatsApp integration  

### WhatsApp (via Twilio)
1. Set up a Twilio account and WhatsApp sandbox.
2. In Twilio Console → Messaging → WhatsApp Sandbox, set the inbound webhook URL to:
    - `POST https://<your-render-service>.onrender.com/webhook/whatsapp` (or `/whatsapp`, both are available)
3. In Render, set env vars: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_WHATSAPP_NUMBER`.
4. Send messages to your Twilio WhatsApp number; responses are returned as TwiML XML.
5. Optional: Send a location message; if Twilio forwards `Latitude`/`Longitude`, the server will include it.

---

## 📖 System & Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a full breakdown of agent roles, request flow, and integration patterns.

---
