import json
from pathlib import Path
from typing import Any, List, Optional

class JSONExporter:
    def __init__(self, indent: Optional[int] = None) -> None:
        self.indent = indent

    def export(self, data: List[dict], path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=self.indent or None)