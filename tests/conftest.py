import os
import pytest

# Ensure no real external calls (user will supply keys at runtime if desired)
for var in ["GOOGLE_GENAI_API_KEY", "GOOGLE_CLOUD_API_KEY"]:
    os.environ.setdefault(var, "")

from agents.supervisor import create_supervisor

@pytest.fixture(scope="session")
def supervisor_instance():
    # Create once per test session
    return create_supervisor()
