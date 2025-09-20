<!-- Copilot instructions for the Kura public-transport demo app -->
# Quick guide for AI coding assistants

This repository implements a small multi-agent transportation assistant (Vaya). It uses:
- an LLM planner to produce step-by-step plans,
- an Executor agent (LangChain-style) that calls `@tool`-decorated functions to perform tasks,
- a dedicated Synthesizer LLM (see `agents/synthesizer.py`) to turn collected snippets/world state into the final reply.
Use these notes to make targeted, low-risk edits and to propose code improvements that match the project's conventions.

Three-agent (A2A) architecture (Planner → Executor → Synthesizer)
---------------------------------------------------------------
This project follows a strict A2A (agent-to-agent) design: each agent is a separate LLM with a single responsibility and they communicate only via typed JSON artifacts.

- Planner (LLM #1): reads the user's query and the current `world_state` snapshot and emits a strict plan.json. The plan is an ordered list of steps (e.g., Geocode, Transit, Weather). Each step must contain the minimal `args` needed and may include `forEach` metadata for multi-stop flows. Planner output MUST be valid JSON and match the `steps` array contract used by `agents/planner.py`.

- Executor (LLM #2): the main agent that executes the plan. Implemented as a LangChain ReAct-style agent in `agents/executor.py`, it receives one step at a time, selects exactly one tool to call with minimal arguments, then returns a JSON object: {"deltaState": {...}, "snippet": "..."}. The PlannerAgent merges each `deltaState` into the canonical `world_state` using `utils/state.deepMerge` before the next step.

- Synthesizer (LLM #3): after all steps run, the Synthesizer reads the final `world_state` and the collected snippets and produces the concise user-facing answer. Keep all natural-language formatting here — do not synthesize inside the Supervisor or Executor.

Wiring and implementation notes
--------------------------------
- Instantiate three `ChatGoogleGenerativeAI` clients (Planner, Executor, Synthesizer) using your Gemini key. Explicitly pass the key to avoid ADC fallbacks, for example:

	ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.2, google_api_key=os.environ["GEMINI_API_KEY"]) 

	This ensures we never fall back to Vertex/ADC.

- Register HTTP tools (Maps, Routes, Weather, Places, Geocoding) as LangChain tools (see `agents/tools/weather_tool.py` for pattern). Use your Google Cloud key for those API calls (prefer `GOOGLE_API_KEY` env var). Tools must be `@tool`-decorated and return raw dicts or raise on errors.

- Enforce single-source-of-truth state updates: always apply tool outputs as small `deltaState` patches and merge them using `utils/state.deepMerge`. Do NOT mutate `world_state` outside of the `deepMerge` path.

- runTurn contract (tight orchestration):
	1. Seed `world_state` with the raw query (e.g., `world_state.query.raw`).
	2. Call the Planner LLM to get `plan.json` (validate JSON strictly).
	3. Build an Executor (LangChain agent) with the full tools list and run each plan step through it.
		 - For each step: call Executor, receive `{deltaState, snippet}`.
		 - Merge `deltaState` into `world_state` via `deepMerge`.
		 - Append `snippet` to a list of snippets for final synthesis.
	4. After all steps, call the Synthesizer LLM with the final `world_state` and collected snippets to produce the final answer.

Logging and observability
-------------------------
- Log the entire plan JSON, then log each Executor tool invocation (tool name, args, response summary), each merged delta (before/after state diff), and the final `world_state`. This tracing makes the agent reasoning auditable.
- Use `utils/logger.get_logger(__name__)` and keep logs under the `kura` root logger so local dev and CI can enable/disable verbosity consistently.

Testing & mocking
-----------------
- Avoid calling LLMs in unit tests. Instead, mock Planner/Executor/Synthesizer clients or inject deterministic LLM wrappers. Mock your `@tool` functions to return representative `deltaState` patches.
- Add a small integration test that runs `runTurn` with a mocked Planner (returns a 2-step plan), a mocked Executor (returns deterministic deltas/snippets), and a real `synthesizer.synthesize` to assert final output formatting.

If any of these wiring details are unclear or you want me to implement the mocked tests / LLM client instantiation changes, tell me which one and I'll update the code and tests accordingly.

Key components
- `main.py` — CLI entry. Routes user input to `agents.planner.runTurn` and handles CLI UX (colorama optional).
- `agents/planner.py` — The PlannerAgent (Planner → Executor orchestration). It coordinates planning and execution and wires the tools into the Executor; it should NOT perform final synthesis itself — that responsibility belongs to `agents/synthesizer.py`.
- `agents/executor.py` — Builds the LangChain-style Executor agent which is the main agent that performs the requested tasks by calling `@tool`-decorated functions (see `agents/tools/*`). Contains the executor prompt contract and helpers `build_executor`, `run_step`, `apply_delta`.
- `agents/synthesizer.py` — Merges specialist snippets into final responses with light heuristics; good place to encode UX phrasing rules.
- `agents/tools/*.py` — Tool wrappers (e.g., `weather_tool.py`) that call external APIs. Tools must raise on error and return raw dicts expected by `SpecialistOut`/world state.
- `utils/contracts.py` — Pydantic models for `WorldState`, specialist inputs/outputs and `Slots`. Any change to runtime state shape should be made here first.
- `utils/state.py` — Utility `deepMerge` implementation used to merge delta states into the world-state dictionary.
- `utils/logger.py` — Simple logging utility; get loggers via `get_logger(name)`.
- `requirements.txt` — Canonical pinned deps used in this project (LLM providers + langchain + pydantic).

-Important conventions (do not break)
- WorldState is the canonical blackboard (see `utils/contracts.py`). Agents and tools exchange JSON-compatible deltas which are merged with `deepMerge` (in `utils/state.py`). When adding fields, update Pydantic models to keep validation clear.
- Executors and planners MUST output parsable JSON. For example, the planner returns {"steps":[{...}]}. `executor.run_step` extracts the first JSON object in the LLM output and treats it as the delta; keep assistant responses strictly JSON when updating prompts. The Executor is the component that should call `@tool` functions and return `deltaState` + `snippet` objects — not the PlannerAgent.
- Tools must not fabricate data. If required arguments (e.g., lat/lng) are missing, they should either add a clear error to `deltaState.errors` or raise a ValueError — the supervisor logs and the synthesizer uses errors for fallbacks.
- LLM choices are centralized: `agents.planner` and `agents/executor` instantiate LLMs. Prefer editing model names and temperature there rather than scattering changes.

Developer workflows and quick commands
- Local dev: create a `.env` in the project root (or copy `.env.example`) and set API keys: `GOOGLE_API_KEY` (required for `weather_tool`).
- Run locally: python -m main (interactive CLI)
- Tests: this project uses pytest (see `requirements.txt`). Run `pytest -q` at the repo root.
- Logging: use `from utils.logger import get_logger` and call `get_logger(__name__)`. The root logger namespace is `kura`.

Integration notes and edge cases
- External APIs: `agents/tools/weather_tool.py` calls Google Weather endpoints and expects `GOOGLE_API_KEY` in env. Network calls use `requests` with a 20s timeout.
- Error handling: PlannerAgent captures exceptions in `runTurn` and returns a user-friendly message. When adding new tools, ensure they surface structured `errors` in `SpecialistOut` so `synthesizer` can generate helpful fallbacks.
- Tests & sandboxing: heavy LLM calls are expensive; prefer adding unit tests that mock LLMs and tools. The code is structured to allow injection of mock tools into `build_executor`.

Concrete examples to follow
- Adding a new tool: create `agents/tools/<name>_tool.py`, expose a `@tool`-decorated callable that returns a dict (raw API response or structured data). Wire the tool into the Executor by including it in the `tools` list passed to `build_executor` (this wiring happens in `agents/planner.py`). The Executor (from `agents/executor.py`) will be the component that invokes the `@tool` during execution.
- Changing planner output shape: update `agents/planner.PLANNER_SYS` instructions and `utils/contracts.SpecialistOut` / `WorldState` to keep Pydantic validation consistent.
- Adjusting synthesis phrasing: modify `agents/synthesizer.py` — it expects snippets and `world_state.context.lastWeather` when present. Keep synthesis logic centralized here: do not move final natural-language formatting into the PlannerAgent or Executor.

What NOT to change without a test or manual validation
- The executor prompt templates and the JSON-output requirements (small changes can break parsing in `run_step`). Also: do not move synthesis responsibilities into the PlannerAgent — keep planning & execution separate from final response generation.
- `WorldState` field names or nested shapes without updating `contracts.py` and related code paths.

Where to look first when debugging
- Reproduce the CLI flow: `main.py` → `agents/planner.runTurn` → planner → executor → tools → synthesizer.
- Check logs (logs/app.log and console) and enable DEBUG by modifying `utils/logger._configure_root` during local debugging.

If anything in these notes is unclear or missing, tell me which part you'd like expanded (examples: more test guidelines, mocking patterns, or prompt-editing safety checks).
