# agents/specialists/weather.py
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import tool
from langchain_core.runnables import Runnable
from utils.helper_func import get_location, local_weather

def create_weather_agent() -> Runnable:
    """Creates a specialist agent for weather forecasts."""
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0,
        google_api_key=os.getenv("GOOGLE_GENAI_API_KEY")
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are a weather specialist. Your job is to find the weather forecast for a given location. Return ONLY a JSON object with the weather details. "
         "Example Response: {{\"location\": \"JFK Airport\", \"forecast\": \"Light Rain\", \"temperature_fahrenheit\": 68}}"),
        ("human", "{query}")
    ])
    
    return prompt | llm | JsonOutputParser()


@tool
def get_weather_for_current_location() -> dict:
    """Fetches the weather for the current location based on IP geolocation."""
    location_data = get_location()
    lat = location_data.get("lat")
    lon = location_data.get("lon")
    if lat is None or lon is None:
        raise ValueError("Could not determine location from IP.")
    
    weather_data = local_weather(lat, lon)
    return {
        "location": f"{location_data.get('city')}, {location_data.get('regionName')}, {location_data.get('country')}",
        "forecast": weather_data.get("weather", [{}])[0].get("description", "No data"),
        "temperature_fahrenheit": round((weather_data.get("main", {}).get("temp", 0) - 273.15) * 9/5 + 32, 2)
    }
# """Sanitizes and logs the output of the weather agent."""
# def _run(x):
#     result = x.get("result", {})
#     if not isinstance(result, dict):
#         raise ValueError("Weather agent returned non-dictionary result.")
#     return result


# weather_agent = create_weather_agent()