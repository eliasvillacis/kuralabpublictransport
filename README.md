# Civic Challenge: Smarter Transit Guidance


## Problem
Modern navigation apps excel at finding the fastest routes, but a rider’s journey is about more than speed. True reliability can be disrupted by subway delays, bus bunching, elevator outages, or temporary street/exit closures—factors that are especially critical for accessibility. Popular apps also rely on continuous GPS tracking, which can drain a device’s battery during longer trips. This project proposes a **Conversational GPS**: an assistant that complements existing navigation by delivering deeper real-time insights in natural language, helping riders travel with more confidence and equity, while being mindful of battery life.


## Challenge Statement
**How can we deliver a reliable, accessible, and battery-efficient Conversational GPS that surfaces real-time delays, closures, and hazards in one assistant?**

## Agent Goals
- Understand natural language requests (e.g., “get me from Astoria to Battery Park, avoid delays”).
- Pull live signals from real-world data sources.
- Compare candidate routes against those signals.
- Recommend the best route with clear rationale and caveats.


## Who Benefits
- Daily commuters, students, and tourists.
- Riders needing fewer transfers or accessible stations.
- City agencies aiming to reduce crowding and improve awareness.


## Success Metrics
- **Accuracy:** Route meets predicted ETA window.
- **Quality:** Recommended route matches btbaseline (e.g., Google Maps ETA) ≥70% of the time.
- **Clarity:** Users rate explanations ≥4/5.
- **Reliability:** p95 latency under 3.5s, error rate under 2%.


---


## High-Level Architecture
This project uses a modular, multi-agent system with a straightforward Agent-to-Agent (A2A) architecture. Each agent specializes in a task and communicates directly with the others. This design avoids the overhead of a separate communication server while allowing us to swap or extend components easily.


- **Router:** Classifies user intent and delegates queries.
- **Maps Agent:** Provides directions and ETAs (Google Routes API).
- **Traffic Agent:** Retrieves incidents and congestion data.
- **Transit Agent:** Monitors GTFS-RT delays and vehicle positions (Transitland).
- **Weather Agent:** Flags hazards affecting travel time (OpenWeather).
- **Composer:** Merges results, ranks routes, and provides the final answer with rationale.


**Data Flow:**
```
User → Router
|-- Maps Agent → routes + ETAs + polylines
|-- Traffic Agent → incidents + congestion
|-- Transit Agent → trip updates + delays
|-- Weather Agent → hazard flags
→ Composer/Ranker → Final Answer + Rationale
```


### Data Sources
- **Routing:** Google Routes API — global routing with traffic-aware ETAs.
- **Transit:** Transitland REST API — aggregated GTFS-RT feeds for real-time delays and vehicle positions.
- **Weather:** OpenWeather API — forecasts, conditions, and hazard alerts.


---


## Technical Design Rationale


### Why A2A (Agent-to-Agent)
- **Simplicity:** One Python backend, easier to scale and maintain.
- **Fewer Moving Parts:** No separate communication server.
- **Performance:** Direct API calls keep latency low.
- **Security:** API keys managed centrally on the backend.
- **Cost:** Fewer services = lower cost.


### When to Consider MCP or Hybrid
- **MCP (Model Context Protocol):** Useful for centralized tool access and logging, especially if multiple teams or agents share the same external APIs.
- **Hybrid (A2A + MCP):** Combines A2A’s flexibility with MCP’s centralized governance and scalability. Ideal for enterprise-scale deployments where reliability, auditing, and security are critical.


For this project, A2A is the best fit: fast to prototype, resilient, and easy to reason about. A hybrid model could be explored later for production scaling.


---


## LangChain vs LangGraph


### Why LangChain
- **Modular Components:** Agents, tools, and chains can be combined cleanly.
- **Agent Tools:** Easy to wrap APIs (Google Routes, Transitland, OpenWeather) as tools for specialized agents.
- **Simplicity:** Perfect for our linear flow (query → agents → composer → answer).


### Why Not LangGraph (Here)
- **Optimized for Non-Linear Workflows:** LangGraph shines when agents need to loop, retry, or backtrack.
- **Extra Overhead:** Requires defining nodes/edges/state transitions, unnecessary for our straightforward pipeline.


**Bottom line:** LangChain gives us all we need to implement this linear, multi-agent system without added complexity.


---