# src/agents/orchestrator/config.py

import os
from jinja2 import Template
from src.tools.get_company_profile_tool import get_company_profile
from src.agents.agent_registry import get_orchestrator_menu

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.jinja2")

with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    _RAW_TEMPLATE = f.read().strip()

# Render the Jinja2 template once at startup,
# injecting the live registry menu into the prompt.
# When a new agent is added to AGENT_REGISTRY,
# the prompt automatically reflects it on next server start.
ORCHESTRATOR_SYSTEM_PROMPT = Template(_RAW_TEMPLATE).render(
    agent_registry_menu=get_orchestrator_menu()
)

OrchestratorConfig = {
    "name": "orchestrator",
    "model": "gpt-4o-mini",
    "max_tokens": 1500,
    "system_prompt": ORCHESTRATOR_SYSTEM_PROMPT,
    "tools": [get_company_profile],
}
