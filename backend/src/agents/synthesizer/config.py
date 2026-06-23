from pathlib import Path

current_dir = Path(__file__).parent
prompt_path = current_dir / "system_prompt.jinja2"

with open(prompt_path, "r", encoding="utf-8") as f:
    system_prompt = f.read()

SynthesizerConfig = {
    "name": "synthesizer",
    "model": "gpt-4o-mini",
    "max_tokens": 2500,        # raised from 700 — dashboard synthesis needs room
    "system_prompt": system_prompt
}
