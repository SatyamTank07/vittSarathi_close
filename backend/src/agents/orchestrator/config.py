import os
from src.tools.get_company_profile_tool import get_company_profile

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.jinja2")

with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    ORCHESTRATOR_SYSTEM_PROMPT = f.read().strip()

OrchestratorConfig = {
    "name": "orchestrator",
    "model": "gpt-4o-mini",
    "max_tokens": 1500,
    "system_prompt": ORCHESTRATOR_SYSTEM_PROMPT,
    "tools": [get_company_profile],
}
