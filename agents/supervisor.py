# agents/supervisor.py
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import CommaSeparatedListOutputParser
from langchain_core.runnables import (
    Runnable, RunnableParallel, RunnablePassthrough, RunnableLambda
)

from utils.logger import get_logger
from .specialists.weather import create_weather_agent
from .specialists.traffic import create_traffic_agent
from .specialists.transit import create_transit_agent
from .specialists.maps import create_maps_agent

logger = get_logger(__name__)
DEBUG_ROUTING = os.getenv("DEBUG_ROUTING", "0") == "1"

def create_supervisor() -> Runnable:
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0.2,
        google_api_key=os.getenv("GOOGLE_GENAI_API_KEY")
    )

    agent_factory_map = {
        "Weather": create_weather_agent,
        "Traffic": create_traffic_agent,
        "Transit": create_transit_agent,
        "Maps": create_maps_agent,
    }

    def wrap_with_log(name, runnable):
        def _run(x):
            if DEBUG_ROUTING:
                q = x.get("query", "")[:120]
                logger.info(f"[AGENT:{name}] invoked | query='{q}'")
            return runnable.invoke(x)
        return RunnableLambda(_run)

    agent_map = {name: wrap_with_log(name, factory()) for name, factory in agent_factory_map.items()}

    agent_names_str = ", ".join(agent_factory_map.keys())
    routing_prompt = ChatPromptTemplate.from_template(
        "You are a supervisor routing user queries. Based on the query and conversation history, "
        "select the necessary specialists from this list: {agent_names}.\n"
        "Respond with a comma-separated list of the required specialist names.\n\n"
        "Conversation History:\n{history}\n\nUser Query: {query}"
    ).partial(agent_names=agent_names_str)

    routing_chain = routing_prompt | llm | CommaSeparatedListOutputParser()

    compiler_prompt = ChatPromptTemplate.from_template(
        "You are a helpful assistant. Synthesize the results from the specialist agents into a single, coherent, and friendly response.\n"
        "Be conversational and natural. Your final response should be in plain text, not JSON.\n\n"
        "Conversation History:\n{history}\n\nUser's Latest Query: {query}\n\nSpecialist JSON Results:\n{results}"
    )
    compiler_chain = compiler_prompt | llm

    def _sanitize_and_log(x):
        picks = x.get("agent_names", [])
        picks = [p.strip() for p in picks if p and p.strip()]
        seen = set()
        picks = [p for p in picks if p in agent_map and not (p in seen or seen.add(p))]
        x["agent_names"] = picks
        if DEBUG_ROUTING:
            q = x.get("query", "")[:120]
            logger.info(f"[ROUTER] query='{q}' -> agents={picks}")
        return x

    def _invoke_selected(x):
        selected = x["agent_names"]
        if not selected:
            return {"note": "No specialists selected. Providing a general response."}
        return RunnableParallel({name: agent_map[name] for name in selected}).invoke(x)

    main_chain = (
        RunnablePassthrough.assign(agent_names=routing_chain)
        | RunnableLambda(_sanitize_and_log)
        | RunnablePassthrough.assign(results=_invoke_selected)
        | compiler_chain
    )
    return main_chain