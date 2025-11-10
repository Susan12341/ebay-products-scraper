from pathlib import Path
from typing import List

import pandas as pd

class ExcelExporter:
    def export(self, data: List[dict], path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(data)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="eBay Data")