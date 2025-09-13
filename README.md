<p align="center">
  <img src="https://img.shields.io/badge/Walk%20With%20Me-🚶‍♀️-222222?style=for-the-badge" alt="Walk With Me" />
</p>

<h1 align="center">✨ Walk With Me ✨</h1>
<p align="center"><i>your lightweight conversational gps — built to guide, not drain 🔋</i></p>

<p align="center">
  <img alt="status" src="https://img.shields.io/badge/status-prototype-blue?style=flat-square">
  <img alt="focus"  src="https://img.shields.io/badge/focus-transit%20insights-6aa84f?style=flat-square">
  <img alt="battery" src="https://img.shields.io/badge/battery-friendly-ffd966?style=flat-square">
</p>

---

<p align="center">
  🚇 <b>real-time transit insights</b> • ♿ <b>accessibility-first updates</b> • 🔔 <b>proactive notifications</b>  
  <br>— all without draining your phone battery —
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

## 👥 Who Benefits  
- 🚇 **daily commuters** without constant charging access  
- 🎒 **students & tourists** new to the system  
- ♿ **accessibility-focused riders** needing outage alerts  
- 🏙️ **city agencies** aiming to reduce crowding & improve awareness  
- 🚗 **drivers (secondary)**: lightweight sms/voice alerts for road closures, incidents, or weather  

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

---

