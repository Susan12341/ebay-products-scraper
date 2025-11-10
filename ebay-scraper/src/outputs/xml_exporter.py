from pathlib import Path
from typing import List
import xml.etree.ElementTree as ET

class XMLExporter:
    def export(self, data: List[dict], path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        root = ET.Element("items")
        for row in data:
            item_el = ET.SubElement(root, "item")
            for k, v in row.items():
                el = ET.SubElement(item_el, k)
                if isinstance(v, list):
                    el_list = ET.SubElement(item_el, f"{k}_list")
                    for i in v:
                        child = ET.SubElement(el_list, "value")
                        child.text = "" if i is None else str(i)
                    # keep original key empty for compatibility
                    el.text = ""
                else:
                    el.text = "" if v is None else str(v)

        tree = ET.ElementTree(root)
        tree.write(path, encoding="utf-8", xml_declaration=True)