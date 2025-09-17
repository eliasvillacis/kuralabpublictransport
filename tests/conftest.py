import os, sys, pathlib, pytest

# Ensure project root on path for 'agents' imports
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force a dummy key so supervisor initialization does not fail in CI
os.environ["GOOGLE_GENAI_API_KEY"] = os.environ.get("GOOGLE_GENAI_API_KEY", "DUMMY_TEST_KEY") or "DUMMY_TEST_KEY"
# Enable deterministic stub behavior (avoid real network calls / LLM usage)
os.environ.setdefault("TEST_MODE", "1")

from agents.supervisor import create_supervisor

@pytest.fixture(scope="session")
def supervisor_instance():
    return create_supervisor()
