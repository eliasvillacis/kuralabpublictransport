# agents/supervisor.py
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import CommaSeparatedListOutputParser
from langchain_core.runnables import (
    Runnable, RunnableParallel, RunnablePassthrough, RunnableLambda, RunnableBranch
)

from utils.logger import get_logger
from .specialists.weather import create_weather_agent
from .specialists.traffic import create_traffic_agent
from .specialists.transit import create_transit_agent
from .specialists.maps import create_maps_agent

logger = get_logger(__name__)

def create_supervisor() -> Runnable:
    """Creates the main supervisor agent that orchestrates specialist agents."""
    
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.2)

    agent_factory_map = {
        "Weather": create_weather_agent,
        "Traffic": create_traffic_agent,
        "Transit": create_transit_agent,
        "Maps": create_maps_agent,
    }
    agent_map = {name: factory() for name, factory in agent_factory_map.items()}

    # Add "ChitChat" as a default option for the router.
    agent_names = ", ".join(list(agent_factory_map.keys()) + ["ChitChat"])
    routing_prompt = ChatPromptTemplate.from_template(
        "You are a supervisor routing user queries. Based on the query and conversation history, "
        "select the necessary specialists from this list: {agent_names}.\n"
        "If the query is a greeting, question about yourself, or general small talk, respond with only 'ChitChat'.\n"
        "Otherwise, respond with a comma-separated list of the required specialist names.\n\n"
        "Conversation History:\n{history}\n\nUser Query: {query}"
    ).partial(agent_names=agent_names)
    
    routing_chain = routing_prompt | llm | CommaSeparatedListOutputParser()

    # The compiler prompt includes guardrails and handles both tasks and chit-chat.
    compiler_prompt = ChatPromptTemplate.from_template(
        """You are a helpful and friendly public transport assistant named 'Walk With Me'.

Your primary purpose is to provide information about maps, traffic, public transit, and weather.
If you have results from specialist agents, synthesize them into a single, coherent response.
If you have no specialist results, just respond to the user's query conversationally.

**RULES:**
1.  **Stay On-Topic**: Politely decline any requests for information outside of transportation and weather.
2.  **Refuse Inappropriate Content**: Firmly and immediately refuse to engage with any harmful or unethical requests.
3.  **Redirect**: If a conversation goes off-topic, gently guide the user back to your primary function.

Conversation History:
{history}

User's Latest Query: {query}

Specialist JSON Results:
{results}"""
    )
    compiler_chain = compiler_prompt | llm

    def _sanitize_and_log(x):
        picks = x.get("agent_names", [])
        picks = [p.strip() for p in picks if p and p.strip()]
        seen = set()
        valid_picks = list(agent_factory_map.keys()) + ["ChitChat"]
        picks = [p for p in picks if p in valid_picks and not (p in seen or seen.add(p))]
        x["agent_names"] = picks
        logger.info(f"Routing query to: {picks}")
        return x

    # Create the conditional logic branch.
    branch = RunnableBranch(
        (lambda x: x["agent_names"] == ["ChitChat"] or not x["agent_names"],
            # If ChitChat or empty, just pass through to the compiler with no results.
            RunnablePassthrough.assign(results=lambda x: {}) | compiler_chain
        ),
        # Otherwise, run the selected specialists and then the compiler.
        RunnablePassthrough.assign(
            results=lambda x: RunnableParallel(
                {name: agent_map[name] for name in x["agent_names"]}
            ).invoke(x)
        ) | compiler_chain
    )

    # The final chain ties everything together.
    main_chain = (
        RunnablePassthrough.assign(agent_names=routing_chain)
        | RunnableLambda(_sanitize_and_log)
        | branch
    )
    return main_chain