from pathlib import Path

current_dir = Path(__file__).parent
prompt_path = current_dir / "system_prompt.jinja2"

with open(prompt_path, "r", encoding="utf-8") as f:
    system_prompt = f.read()

QuantitativeConfig = {
    "name": "quantitative",
    "model": "gpt-3.5-turbo",
    "max_tokens": 700,
    "system_prompt": system_prompt
}
