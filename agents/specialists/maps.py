# agents/specialists/maps.py
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable
import os

def create_maps_agent() -> Runnable:
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0,
        google_api_key=os.getenv("GOOGLE_GENAI_API_KEY"),
    )

    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are a mapping specialist. Your job is to determine the best route based on a user query and return ONLY a JSON object with the route details. "
         "Example Response: {{\"route\": \"I-495 E\", \"eta_minutes\": 55, \"distance_miles\": 22}}"),
        ("human", "{query}")
    ])
    
    return prompt | llm | JsonOutputParser()