# agents/specialists/transit.py
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable

def create_transit_agent() -> Runnable:
    """Creates a specialist agent for public transit."""
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are a public transit specialist. Your job is to find information about bus or train services. Return ONLY a JSON object with the transit details. "
         "Example Response: {{\"line\": \"L Train\", \"status\": \"Delayed\", \"delay_minutes\": 15}}"),
        ("human", "{query}")
    ])
    
    return prompt | llm | JsonOutputParser()