<p align="center">
  <img src="https://img.shields.io/badge/Walk%20With%20Me-🚶-black?labelColor=222" alt="Walk With Me" />
</p>

<h1 align="center">Walk With Me</h1>
<p align="center"><i>A lightweight conversational GPS that complements existing navigation apps.</i></p>

<p align="center">
  <img alt="status" src="https://img.shields.io/badge/status-prototype-blue">
  <img alt="focus"  src="https://img.shields.io/badge/focus-transit%20insights-6aa84f">
  <img alt="battery" src="https://img.shields.io/badge/battery-friendly-ffd966">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-888">
</p>

<blockquote>
<b>Tagline:</b> Real-time transit insights, accessibility updates, and proactive notifications — without draining your battery.
</blockquote>

<p><b>Civic Challenge:</b> <i>Smarter Transit Guidance</i></p>

---

## Problem
Modern navigation apps excel at finding the fastest routes, but a rider’s journey is about more than speed. True reliability can be disrupted by subway delays, bus bunching, elevator outages, or temporary street/exit closures—factors that are especially critical for accessibility.

For drivers, running a full navigation app is rarely an issue: cars often supply charging through built-in systems, and platforms like CarPlay or Android Auto handle continuous GPS in the background.

But **commuters and transit riders face different constraints**. Keeping a navigation app open drains phone batteries quickly, and many don’t have reliable charging access during long trips. Riders need a lighter alternative: one that surfaces critical insights — delays, hazards, accessibility — **without requiring a map to run in the background the whole time**.

This project proposes a **Conversational GPS**: a lightweight assistant that complements (not competes with) existing navigation apps. Instead of replacing Google Maps or Citymapper, it supplements them by delivering real-time insights in natural language. Riders can interact with the assistant to surface **delays, hazards, and accessibility context**, while still relying on their preferred visual navigation app for turn-by-turn guidance.

Users can also receive proactive updates through **Twilio SMS/voice notifications**, keeping them informed without needing to constantly reopen a map app. The goal is not to replicate full GPS navigation but to enhance it — helping riders travel with more confidence, clarity, and equity while being mindful of device battery life.

## Challenge Statement
**How can we deliver a reliable, accessible, and battery-efficient Conversational GPS that surfaces real-time delays, closures, hazards, and weather context in one assistant?**

## Agent Goals
- Understand natural language requests (e.g., “get me from Astoria to Battery Park, avoid delays”).
- Pull live signals from real-world data sources.
- Compare candidate routes against those signals.
- Provide conversational answers with clear rationale and caveats.
- Push proactive updates to users via Twilio.
- Act as a supplement to existing map/navigation apps, not a replacement.

## Who Benefits
- **Transit commuters** who can’t keep their map apps open all day.
- **Students and tourists** unfamiliar with local service patterns.
- **Accessibility-focused riders** needing elevator/outage updates.
- **City agencies** aiming to reduce crowding and improve awareness.
- **Drivers (secondary use):** while drivers typically have chargers and in-car systems, the same architecture could extend to **lightweight voice/SMS alerts** for road closures, incidents, or weather.

## Success Metrics
- **Accuracy:** Route meets predicted ETA window.
- **Quality:** Recommended route matches baseline (e.g., Google Maps ETA) ≥70% of the time.
- **Clarity:** Users rate explanations ≥4/5.
- **Reliability:** p95 latency under 3.5s, error rate under 2%.

---

## High-Level Architecture

This project uses a **Supervisor-led Agent-to-Agent (A2A)** architecture. The **Supervisor** serves as the main communicator — handling **routing** (intent classification), **coordination** (delegating tasks to specialists), and **compilation** (merging outputs into a coherent response).

### Specialists
- **Maps Agent (`maps.py`)** — Provides directions and ETAs (Google Routes API).
- **Traffic Agent (`traffic.py`)** — Retrieves incidents and congestion data.
- **Transit Agent (`transit.py`)** — Monitors GTFS-RT delays and vehicle positions (Transitland).
- **Weather Agent (`weather.py`)** — Flags hazards affecting travel time (OpenWeather).
- **Notifier Agent (Twilio)** — Sends SMS/voice alerts for proactive updates.

**Data Flow:**
```
User → Supervisor (router + compiler)
    |-- Maps Agent → routes + ETAs + polylines
    |-- Traffic Agent → incidents + congestion
    |-- Transit Agent → trip updates + delays
    |-- Weather Agent → hazard flags
    |-- Notifier Agent → SMS/voice alerts
→ Supervisor (final composition) → Conversational Answer
```

### Data Sources
- **Routing:** Google Routes API — traffic-aware ETAs.
- **Transit:** Transitland REST API — GTFS-RT feeds for delays and vehicle positions.
- **Weather:** OpenWeather API — forecasts, conditions, and hazard alerts.
- **Messaging:** Twilio API — SMS and voice notifications.

---

## Visual Layer (Optional, Back Pocket)

While the core experience is conversational, **visual context is important for navigation**. This project includes the option for a **lightweight visual pane** to complement the assistant:

- Built with **Leaflet or MapLibre**.
- Renders JSON from the Supervisor:
  - Route polylines.
  - Incident markers (e.g., delays, closures).
  - Accessibility icons for stations.
  - Weather overlays or alerts.
- Includes a **“Open in Google Maps”** button for turn-by-turn navigation.
- Can also generate **static map images** or **deep links** for Twilio SMS updates.

This ensures the product stays **lightweight and supplemental** — enhancing core map apps rather than duplicating their functionality.

---

## Technical Design Rationale

### Why A2A (Supervisor-led)
- **Simplicity:** All logic centralized in one Python backend.
- **Supervisor Control:** Single orchestrator reduces complexity.
- **Performance:** Direct agent calls keep latency low.
- **Security:** API keys handled in one place.
- **Cost:** Minimal infrastructure overhead.

### When to Consider MCP or Hybrid
- **MCP (Model Context Protocol):** Best for standardized governance, shared tools, and observability at enterprise scale.
- **Hybrid (A2A + MCP):** A future option if scaling requires centralized logging, auditing, or compliance.

For this prototype, **Supervisor-led A2A** is the right fit: fast to build, resilient, and easy to reason about. For production, MCP or hybrid integration could be explored.

---

## LangChain vs LangGraph

### Why LangChain
- **Modular:** Easy to wrap each specialist as a tool.
- **Linear Flow:** Perfect for request → agents → supervisor → answer.
- **Ease of Prototyping:** Keeps development simple and fast.

### Why Not LangGraph (Here)
- **Extra Overhead:** Defining nodes/edges/state adds complexity.
- **Non-Linear Focus:** Better suited for workflows requiring retries, loops, or backtracking.


**Bottom line:** LangChain supports our current linear system well; LangGraph may be revisited if future workflows demand more complex orchestration.



