# main.py
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Load environment variables FIRST
load_dotenv()

# Import logger and supervisor AFTER loading env
from utils.logger import get_logger
from agents.supervisor import create_supervisor

logger = get_logger("main")

# --- Application Setup ---
supervisor = create_supervisor()
chat_history = []

def handle_message(user_query: str) -> str:
    # Create a structured list of message objects for the agent's memory
    recent_history_objects = []
    for msg in chat_history[-6:]: # Use last 3 turns of history
        if msg.startswith("User:"):
            recent_history_objects.append(HumanMessage(content=msg[6:]))
        elif msg.startswith("Assistant:"):
            recent_history_objects.append(AIMessage(content=msg[11:]))

    # Invoke the supervisor with the query and structured history
    response = supervisor.invoke({
        "query": user_query,
        "history": recent_history_objects
    })
    
    # Store the new turn in our simple in-memory list
    chat_history.append(f"User: {user_query}")
    chat_history.append(f"Assistant: {response.content}")
    
    return response.content

# --- Example Command-Line Conversation Loop ---
if __name__ == "__main__":
    logger.info("Assistant starting and waiting for input...")
    
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                print("Assistant: Goodbye!")
                break
            
            assistant_response = handle_message(user_input)
            print(f"Assistant: {assistant_response}")

        except Exception as e:
            logger.error("Error in main loop", exc_info=True)
            print(f"An error occurred: {e}")
            break