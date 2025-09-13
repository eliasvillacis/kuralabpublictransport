# agents/specialists/traffic.py
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable

def create_traffic_agent() -> Runnable:
    """Creates a specialist agent for real-time vehicle traffic."""
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are a traffic specialist. Your job is to find real-time road traffic conditions for a given route or area. Return ONLY a JSON object with traffic details. "
         "Example Response: {{\"condition\": \"heavy\", \"delay_minutes\": 25, \"reason\": \"congestion near exit 15\"}}"),
        ("human", "{query}")
    ])
    
    return prompt | llm | JsonOutputParser()