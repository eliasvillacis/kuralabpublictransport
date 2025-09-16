<p align="center">
  <img src="https://img.shields.io/badge/Vaya-1.0-222222?style=for-the-badge" alt="Vaya" />
</p>

<h1 align="center">🚉 Vaya 🗺️</h1>

*A conversational AI assistant for urban navigation and city travel*

## 🌆 About Vaya

Vaya is a smart travel companion designed for navigating urban environments through natural conversation. Whether you're walking through downtown, catching public transit, or exploring a new neighborhood, Vaya provides intelligent routing suggestions, real-time conditions, and contextual travel insights.

Unlike traditional GPS apps that focus solely on driving directions, Vaya prioritizes pedestrian-friendly routes, public transportation options, and local travel conditions that matter to city dwellers and visitors.

## ✨ What Vaya Does

- 🚶 **Smart Urban Routing**: Get walking directions that consider sidewalks, crosswalks, and pedestrian safety
- 🚇 **Transit Intelligence**: Real-time public transportation schedules, delays, and service updates  
- 🌤️ **Weather-Aware Planning**: Route suggestions that factor in current weather conditions
- 🗣️ **Natural Conversation**: Ask questions like "How do I get downtown?" or "What's the best way to the museum?"
- 🏙️ **City-Focused**: Optimized for urban environments where walking and transit are primary travel modes
- 📱 **Lightweight**: Get travel info without keeping heavy map apps running constantly

## 🚀 Getting Started

### Prerequisites
- Docker and Docker Compose (recommended)
- OR Python 3.8+ for local development
- Google Cloud API key (for Maps and Weather services)
- Google Gemini API key (for AI functionality)

### Quick Setup

**1. Clone and configure:**
```bash
git clone https://github.com/eliasvillacis/kuralabpublictransport.git
cd kuralabpublictransport
cp .env.example .env
# Edit .env with your API keys
```

**2. Run with Docker (recommended):**
```bash
docker-compose up -d
```

**3. Access the service:**
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Chat endpoint: POST to http://localhost:8000/chat

### Local Development (VS Code/Python)
- Recommended for fast iteration and debugging
- Python 3.8+ required

```bash
git clone https://github.com/eliasvillacis/kuralabpublictransport.git
cd kuralabpublictransport
cp .env.example .env
# Edit .env with your API keys
pip install -r requirements.txt
python server.py  # Web API
# OR
python main.py    # Console interface
```

### Docker Deployment (Production/Team)
- For consistent, production-like environment

```bash
docker-compose up -d
# View logs
docker-compose logs -f
# Stop and cleanup
docker-compose down
```

## 🛠️ Technical Stack & APIs
- 🤖 **AI Engine**: Google Gemini (LLM, NLU/NLG)
- 🌐 **Web Framework**: FastAPI (API endpoints, future web UI backend)
- 🗺️ **Google APIs**:
  - Geocoding API (address/place to lat/lon)
  - Maps Static API (map images, for web UI)
  - Routes API (routing, directions, traffic info)
  - Places API (place search, autocomplete)
  - Weather API (current/forecast conditions)
  - Geolocation API (device/IP-based location)
- 🚇 **Transitland API**: Public transit schedules/updates
- 🔄 **Architecture**: Multi-agent system with centralized intelligence
- 🐳 **Deployment**: Docker with auto-restart

## 🏗️ Project Structure
```
📂 agents/
  ├─ 🎭 supervisor.py     # Main orchestrator & routing
  └─ 📂 specialists/
     ├─ 🗺️ maps.py       # Location & routing
     ├─ 🚇 transit.py    # Public transit
     └─ 🌤️ weather.py    # Weather conditions
📂 utils/
  ├─ 📝 logger.py        # Logging utilities
  └─ 🗺️ google_maps.py   # Maps API integration
📄 server.py             # FastAPI web server
📄 main.py              # Console interface
📄 docker-compose.yml   # Container orchestration
```

## 💡 The Urban Navigation Challenge

City travel is different from suburban driving. Urban travelers need:

- 🚶 **Pedestrian-first routing** that considers sidewalks, stairs, and safe crossings
- 🚇 **Real-time transit updates** for buses, trains, and shared mobility
- 🌧️ **Weather-aware suggestions** for outdoor walking vs. covered routes  
- 🏗️ **Construction awareness** for temporary closures and detours
- ♿ **Accessibility considerations** for mobility-friendly paths
- 🔋 **Battery efficiency** without constantly running heavy map applications

Vaya addresses these needs through conversational AI that understands the nuances of city navigation, providing thoughtful recommendations that go beyond simple point-to-point directions.

## 🎯 Perfect For

- 🏙️ **Urban Commuters**: Daily travelers who rely on walking and public transit
- 🎒 **City Visitors**: Tourists exploring unfamiliar neighborhoods and transit systems  
- 🚶 **Pedestrians**: Anyone who prioritizes walking routes over driving directions
- ♿ **Accessibility Users**: Travelers who need mobility-friendly route information
- 🌱 **Eco-conscious**: People choosing sustainable transportation options
- 📱 **Battery-conscious**: Users wanting travel info without heavy GPS apps

## 🏗️ How It Works

Vaya uses a smart multi-agent architecture where a central supervisor coordinates specialized components:

```
User Request → Supervisor (AI) → Specialists → Live Data → Response
```

### Agent Specialists
- 🗺️ **Maps**: Routing, directions, and location services (Geocoding API, Routes API, Maps Static API, Places API)
- 🚇 **Transit**: Public transportation schedules and updates (Transitland API)
- 🌦️ **Weather**: Conditions that affect travel decisions (Weather API)
- 📍 **Location**: Device/IP-based geolocation (Geolocation API)

## 🔧 Environment Setup

Create a `.env` file with:
```env
# Required API Keys
GOOGLE_GENAI_API_KEY=your_gemini_api_key_here
GOOGLE_CLOUD_API_KEY=your_google_cloud_api_key_here

# Optional Configuration  
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
```

## 📡 Using the API

### Chat Endpoint
Send natural language requests to get travel assistance:

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I need to get from Brooklyn to Manhattan, what are my options?",
    "session_id": "user123"
  }'
```

### Example Conversations
- *"How do I get to Central Park from Times Square?"*
- *"What's the weather like for walking to work today?"*
- *"I'm at Union Square, how do I get to the airport?"*
- *"Best way to Brooklyn Bridge from here?"*

## 🐳 Docker Deployment

The project includes full Docker support:

```bash
# Build and run
docker-compose up -d

# View logs  
docker-compose logs -f

# Stop and cleanup
docker-compose down
```

## 🔮 Roadmap

- 🌐 **Web Interface**: Clean, responsive chat UI
- 🗺️ **Visual Integration**: Lightweight map overlays  
- 🔔 **Proactive Alerts**: Route disruption notifications
- 🚇 **Enhanced Transit**: Real-time arrival predictions
- ♿ **Accessibility**: Comprehensive mobility support

## 🏗️ Architecture

For detailed technical information about the multi-agent architecture, design decisions, and implementation details, see [ARCHITECTURE.md](./ARCHITECTURE.md).

---

<p align="center">
  🚶 <b>pedestrian-focused</b> • 🚇 <b>transit-integrated</b> • 🗣️ <b>conversational</b>
</p>

<p align="center">
  <i>Navigate the city, naturally</i>
</p>