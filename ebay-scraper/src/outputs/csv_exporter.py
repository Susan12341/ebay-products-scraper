from pathlib import Path
from typing import List

import pandas as pd

class CSVExporter:
    def export(self, data: List[dict], path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(data)
        df.to_csv(path, index=False)