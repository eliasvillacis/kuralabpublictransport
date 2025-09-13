<p align="center">
  <img src="https://img.s➡️ riders need a **smart companion**: one that surfaces critical insights and helps navigate transit systems effectively.lds.io/badge/Vaya-1.0-222222?style=for-the-badge" alt="Vaya" />
</p>

<h1 align="center">🚉 Vaya 🗺️</h1>

## 🛠️ Technical Stack
- 🤖 **AI Engine**: Google Gemini for natural language understanding
- 🗺️ **Location Services**: Google Maps API for routing
- 🚇 **Transit Data**: Transitland API for real-time updates
- 🔄 **Architecture**: Multi-agent system with specialized components

## 🏗️ Project Structure
```
📂 agents/
  ├─ 🎭 supervisor.py     # Main orchestrator
  └─ 📂 specialists/
     ├─ 🗺️ maps.py       # Location & routing
     ├─ 🚦 traffic.py    # Traffic conditions
     ├─ 🚇 transit.py    # Public transit
     └─ 🌤️ weather.py    # Weather conditions
📂 utils/
  └─ 📝 logger.py        # Logging utilities
```

---

<p align="center">
  🚇 <b>real-time transit insights</b> • ♿ <b>accessibility-first updates</b> • 🔔 <b>proactive notifications</b>
</p>

<p align="center">
  <i><b>Civic Challenge:</b> smarter transit guidance</i>
</p>

---

## 💡 Problem  
modern navigation apps excel at finding the *fastest* route, but riders need more than speed:  

- subway delays 🚉  
- bus bunching 🚌  
- elevator outages ♿  
- temporary closures 🚧  

for drivers, continuous gps isn’t an issue — cars have chargers and dashboards. but **commuters and transit riders face real constraints**. keeping maps open quickly drains batteries, and portable charging isn’t always an option.  

➡️ riders need a **lighter companion**: one that surfaces critical insights without demanding a full map running in the background.  

---

## 🎯 Challenge Statement  
**how can we deliver a reliable, accessible, and battery-friendly conversational gps that surfaces delays, closures, hazards, and weather context in one assistant?**  

---

## 🛠️ Agent Goals  
- 🗣️ understand natural requests (“get me from astoria to battery park, avoid delays”)  
- 🔎 pull live signals from real data (transitland, openweather, google routes)  
- ⚖️ compare candidate routes against disruptions  
- 💬 respond in clear, conversational language with caveats  
- 📲 push proactive updates via twilio sms/voice  
- 🗺️ supplement — not replace — existing map apps  

---

## 🚀 Getting Started
1. Clone the repository
2. Create a `.env` file with your API keys:
   ```
   GOOGLE_GENAI_API_KEY=your_key
   GOOGLE_CLOUD_API_KEY=your_key
   TRANSITLAND_API_KEY=your_key
   ```
3. Install dependencies: `pip install -r requirements.txt`
4. Run the assistant: `python main.py`

## 🎯 Use Cases
- 🎒 **Commuters**: Get real-time updates about your regular routes
- 🏃 **Tourists**: Navigate unfamiliar transit systems with ease
- ♿ **Accessibility Users**: Stay informed about elevator status and accessible routes
- 🌧️ **Weather-conscious**: Get route recommendations based on current conditions

---

## 📊 Success Metrics  
- **accuracy** ✅ routes match predicted eta  
- **quality** 🌟 recommended route matches google ≥70%  
- **clarity** 🗣️ explanations rated ≥4/5  
- **reliability** ⚡ p95 latency <3.5s, error rate <2%  

---

## 🏗️ High-Level Architecture  

```
User → Supervisor (router + compiler)
    ├─ Maps Agent     → routes + ETAs
    ├─ Traffic Agent  → incidents + congestion
    ├─ Transit Agent  → trip updates + delays
    ├─ Weather Agent  → hazard flags
    └─ Notifier Agent → SMS/voice alerts
          ↓
       Final conversational answer
```


### 🔹 Specialists  
- 🗺️ **maps.py** → directions & ETAs (Google Routes)  
- 🚦 **traffic.py** → incidents & congestion  
- 🚇 **transit.py** → GTFS-RT trip updates (Transitland)  
- 🌦️ **weather.py** → hazard flags (OpenWeather)  
- 📲 **notifier** → proactive sms/voice (Twilio)  

---

## 🗺️ Visual Layer (Optional)  
while the heart is conversational, a lightweight visual pane can:  

- render routes & delays with **Leaflet/MapLibre**  
- show icons for closures, incidents, elevators  
- overlay weather hazards  
- deep-link “open in google maps” buttons  
- generate static map images for twilio sms  

---

## 🤔 Technical Design Rationale  

### why A2A  
- 🎯 **simplicity:** centralized in one backend  
- 👩‍✈️ **supervisor control:** routing + orchestration in one place  
- ⚡ **performance:** low latency direct calls  
- 🔐 **security:** api keys stored once  
- 💰 **cost:** minimal infra overhead  

### when to consider MCP or hybrid  
- **MCP:** governance & observability at enterprise scale  
- **Hybrid:** if scaling demands shared logging/auditing  

---

## 🧩 LangChain vs LangGraph  

- **LangChain**: modular, linear flow, great for prototyping  
- **LangGraph**: powerful but heavier, best for retries/loops/backtracking  

👉 for this prototype: **LangChain** keeps it fast, lean, and easy to extend.
