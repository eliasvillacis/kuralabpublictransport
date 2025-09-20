"""
A2A-enabled CLI entry for the Vaya transportation assistant.

This version uses the A2A (Agent-to-Agent) coordinator for true peer-to-peer
agent communication, with replanning capabilities and persistent memory.
"""

from dotenv import load_dotenv
import os
from typing import Optional
# Load environment variables from project root .env
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=dotenv_path)

from utils.logger import get_logger
from agents.coordinator import get_coordinator
from agents.agents import PlanningAgent, ExecutionAgent, SynthesisAgent

# Set up logger
logger = get_logger(__name__)

# Enable colorized CLI output if colorama is available
try:
    from colorama import Fore, Back, Style, init
    init(autoreset=True)
    COLORS_AVAILABLE = True
except ImportError:
    # Fallback: No color support
    class MockColors:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    Fore = Back = Style = MockColors()
    COLORS_AVAILABLE = False

def initialize_a2a_system():
    """Initialize the A2A coordinator with all agents."""
    coordinator = get_coordinator()

    # Register agents
    coordinator.register_agent(PlanningAgent())
    coordinator.register_agent(ExecutionAgent())
    coordinator.register_agent(SynthesisAgent())

    logger.info("A2A system initialized with agents: planner, executor, synthesizer")
    return coordinator

def print_welcome():
    """
    Print a welcoming startup message with color and usage tips.
    """
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.YELLOW}🤖 VAYA A2A TRANSPORTATION ASSISTANT")
    print(f"{Fore.CYAN}{'='*60}")
    print(f"{Fore.WHITE}Your AI-powered companion with A2A multi-agent architecture!")
    print(f"\n{Fore.GREEN}✨ Enhanced Features:")
    print(f"{Fore.WHITE}   🔄 Dynamic replanning based on execution results")
    print(f"{Fore.WHITE}   🧠 Persistent conversation memory")
    print(f"{Fore.WHITE}   🤝 True agent-to-agent communication")
    print(f"{Fore.WHITE}   📊 Real-time state sharing")
    print(f"\n{Fore.GREEN}💬 I can help you with:")
    print(f"{Fore.WHITE}   🌤️  Weather conditions and forecasts")
    print(f"{Fore.WHITE}   🚗 Traffic and route information")
    print(f"{Fore.WHITE}   🚌 Public transit schedules")
    print(f"{Fore.WHITE}   📍 Location-based services")
    print(f"\n{Fore.MAGENTA}💡 Commands: {Fore.WHITE}'exit' or 'quit' to end, 'reset' to clear memory")
    print(f"{Fore.WHITE}   'memory' to view conversation history, 'status' for system info")
    print(f"{Fore.CYAN}{'-'*60}\n")

def print_goodbye():
    """
    Print a friendly goodbye message with color.
    """
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.GREEN}👋 Thank you for using Vaya A2A Assistant!")
    print(f"{Fore.WHITE}   Your conversation has been saved to memory.")
    print(f"{Fore.CYAN}{'='*60}\n")

def handle_special_commands(user_input: str, coordinator) -> Optional[str]:
    """Handle special CLI commands."""
    command = user_input.lower().strip()

    if command == "memory":
        context = coordinator.get_memory_context()
        print(f"\n{Fore.BLUE}📚 Conversation Memory:")
        print(f"{Fore.WHITE}Recent messages: {len(context.get('recent_messages', []))}")
        print(f"Agent interactions: {len(context.get('agent_interactions', []))}")
        print(f"World state snapshots: {len(context.get('world_state_history', []))}")
        return None

    elif command == "status":
        print(f"\n{Fore.BLUE}🔧 System Status:")
        print(f"{Fore.WHITE}Active agents: {list(coordinator.agents.keys())}")
        print(f"Memory file: data/conversation_memory.json")
        print(f"Replanning: {'Enabled' if coordinator.replanning_enabled else 'Disabled'}")
        return None

    elif command == "reset":
        coordinator.reset_conversation()
        print(f"{Fore.YELLOW}🔄 Conversation memory reset. Starting fresh!")
        return None

    return user_input

def main():
    """Main CLI loop with A2A coordination."""
    logger.info("A2A Transportation Assistant starting up...")

    # Initialize A2A system
    coordinator = initialize_a2a_system()

    # Display welcome message
    print_welcome()

    while True:
        try:
            # Enhanced prompt with color and emoji
            user_input = input(f"{Fore.BLUE}🗨️  You: {Fore.WHITE}").strip()

            # Handle empty input
            if not user_input:
                print(f"{Fore.CYAN}💭 Assistant: {Fore.WHITE}I'm here and listening! Feel free to ask me anything about transportation, weather, or travel.\n")
                continue

            # Handle special commands
            processed_input = handle_special_commands(user_input, coordinator)
            if processed_input is None:
                continue

            # Handle exit commands
            if processed_input.lower() in ["exit", "quit", "bye", "goodbye"]:
                print_goodbye()
                break

            try:
                # Process through A2A coordinator
                print(f"{Fore.MAGENTA}🔄 Processing through A2A agents...")
                assistant_response = coordinator.process_user_query(processed_input)

                print(f"{Fore.GREEN}🤖 Assistant: {Fore.WHITE}{assistant_response}\n")

                # Show agent activity summary
                context = coordinator.get_memory_context()
                recent_interactions = context.get('agent_interactions', [])
                if recent_interactions:
                    print(f"{Fore.CYAN}📊 Agent Activity: {len(recent_interactions)} interactions in this turn\n")

            except Exception as e:
                logger.error(f"Error in A2A processing: {e}")
                print(f"{Fore.RED}⚠️  Assistant: {Fore.WHITE}I encountered an issue with the A2A system. Please try rephrasing or try again!\n")

        except KeyboardInterrupt:
            print_goodbye()
            break
        except Exception as e:
            logger.error(f"Error reading input: {e}")
            print(f"{Fore.RED}❌ Assistant: {Fore.WHITE}Something unexpected happened. Let's try again!")

if __name__ == "__main__":
    main()