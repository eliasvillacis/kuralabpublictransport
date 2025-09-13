# agents/specialists/weather.py
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable

def create_weather_agent() -> Runnable:
    """Creates a specialist agent for weather forecasts."""
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are a weather specialist. Your job is to find the weather forecast for a given location. Return ONLY a JSON object with the weather details. "
         "Example Response: {{\"location\": \"JFK Airport\", \"forecast\": \"Light Rain\", \"temperature_fahrenheit\": 68}}"),
        ("human", "{query}")
    ])
    
    return prompt | llm | JsonOutputParser()