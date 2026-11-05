import json
from pathlib import Path

from app.main import app

output = Path("docs/api/v0.1-openapi.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
