"""Starts the real HTTP service with the STUB model. For end-to-end tests of the web stack without an LLM key."""
import uvicorn

from africa_extension_agent.service import create_app
from tests.stub_model import make_stub

if __name__ == "__main__":
    uvicorn.run(create_app(model_override=make_stub()), host="127.0.0.1", port=8000, log_level="warning")
