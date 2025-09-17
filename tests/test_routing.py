def run_query(supervisor, text):
    context = {"input": text, "history": [], "client_info": {"platform": "test"}}
    return supervisor(context)


def extract_agent_names(result):
    if isinstance(result, dict):
        return result.get("agent_names") or result.get("agents")
    return None


def test_weather_routing_single_location(supervisor_instance):
    res = run_query(supervisor_instance, "what's the weather in Nairobi")
    agents = extract_agent_names(res)
    assert agents and any("weather" in a.lower() for a in agents)
    assert "Nairobi".lower() in str(res).lower()


def test_weather_routing_multi_location(supervisor_instance):
    res = run_query(supervisor_instance, "compare weather in Paris and Rome")
    agents = extract_agent_names(res)
    assert agents and any("weather" in a.lower() for a in agents)
    # Expect both city names mentioned
    body = str(res).lower()
    assert "paris" in body and "rome" in body


def test_chitchat_routing(supervisor_instance):
    res = run_query(supervisor_instance, "how are you doing today?")
    agents = extract_agent_names(res)
    assert agents and any("chit" in a.lower() for a in agents), f"Agents: {agents}"


def test_mixed_greeting_weather(supervisor_instance):
    res = run_query(supervisor_instance, "hey there can you tell me the weather in London")
    agents = extract_agent_names(res)
    assert agents and any("weather" in a.lower() for a in agents)
    assert "london" in str(res).lower()


def test_fallback_when_no_keys(supervisor_instance):
    # If LLM key missing, supervisor should still produce some response (likely chit-chat fallback or structured).
    res = run_query(supervisor_instance, "tell me a joke")
    assert res  # Non-empty
    text = str(res).lower()
    assert any(keyword in text for keyword in ["sorry", "can't", "assist", "joke", "hello", "hi"])
