# 🚶‍♀️ Vaya - Your Urban Navigation Companion

**A lightweight, AI-powered complement to traditional navigation apps.** Get real-time weather, location info, and navigation guidance without draining your battery or overheating your phone.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)

## ✨ What is Vaya?

Vaya is your smart urban companion that **complements** traditional navigation apps. While maps apps focus on visual navigation, Vaya provides conversational intelligence:

- 🌤️ **Real-time weather** at your location or destination
- 📍 **Smart location services** without constant GPS tracking
- 🧠 **AI-powered conversations** that understand your needs
- 🔋 **Battery-friendly** - uses APIs efficiently, not constant location tracking
- 📱 **Lightweight** - no heavy maps rendering or background processes

### Why Vaya?

Vaya works alongside your favorite navigation apps, providing what they can't:

| Traditional Maps Apps | Vaya |
|----------------------|------:|
| 🔋 Heavy battery drain | ⚡ API-efficient, minimal battery use |
| 🌡️ Device overheating | ❄️ Lightweight processing |
| 🗺️ Full map rendering | 💬 Conversational interface |
| 📍 Constant GPS tracking | 🎯 Smart, on-demand location |
| 💾 Large app size | 🪶 Minimal footprint |

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up API Keys

Copy the example `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
# Edit .env and add your keys
# GEMINI_API_KEY=your_gemini_api_key_here
# GOOGLE_API_KEY=your_google_api_key_here
```

### 3. Start Vaya (local)

```bash
python main.py
```

### 4. Try It Out (example interactions)

```
🗨️  You: What's the weather like?
🤖 Assistant: It's currently 75°F and sunny at your location.

🗨️  You: Where am I?
🤖 Assistant: You're at approximately 40.7128°N, 74.0060°W (New York City area).
```

## 💬 What Can Vaya Do?

- Provide current weather and forecasts for your location or destinations
- Geocode place names and resolve coordinates
- Give public transit and routing suggestions (where transit data is available)
- Maintain short-term conversation memory and preferences

## 🏗️ How It Works

Vaya uses a **multi-agent A2A (Agent-to-Agent)** architecture where specialized agents work together:

- **Planning Agent**: Creates execution plans from user queries
- **Execution Agent**: Calls external APIs (weather, geocoding, etc.) using small, focused tools
- **Synthesis Agent**: Produces natural-language responses from the world state
- **Coordinator**: Manages agent interactions, replanning, and memory

### Processing Flow
1. User asks a question
2. Planner makes a plan (geolocate/geocode, weather, transit)
3. Executor runs the plan and updates WorldState
4. Synthesizer converts the final WorldState into a user-facing message

## 📋 Requirements

### Option 1: Native Python
- Python 3.8 or higher (3.11 recommended)
- API Keys: Google Gemini API + Google Cloud API
- Internet access for API calls

### Option 2: Docker (Recommended)
- Docker 20.10+ and Docker Compose 2.0+
- Use the `.env` file for credentials (see `.env.example`)

**Benefits of Docker:** reproducible environment, easy deployments, and no local Python version conflicts.

## 🐳 Docker (quick)

Copy `.env.example` to `.env`, fill in API keys, then build and start with Docker Compose:

```bash
cp .env.example .env
docker-compose up --build
```

Persistent data (conversation memory) and logs are stored in `./data` and `./logs` via volumes.

## 🛠️ Advanced Usage

### CLI Commands

```bash
python main.py  # Interactive CLI
# Commands available: exit/quit, reset, memory, status
```

### Configuration

You can toggle coordinator behavior in `main.py` or the coordinator module (e.g., `replanning_enabled`, `max_iterations`).

### Testing

```bash
pytest  # Run project tests
```

<!-- Troubleshooting removed to keep README concise. See the project's README or docs for troubleshooting tips. -->

## 📊 Architecture (For Developers)

Vaya's architecture centers on a shared WorldState (blackboard) updated by agents. Tools return deltaState patches and `deepMerge()` is used to apply them.

```
User Query → Coordinator → Planning Agent → Execution Agent → Synthesis Agent → Response
```

### Tech Stack
- Python, LangChain, Google Gemini (LLM), Google Cloud APIs (geocoding, weather)

## 🙏 Acknowledgments

Made with ❤️ for urban explorers who want smart navigation without the battery drain.