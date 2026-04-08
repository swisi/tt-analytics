from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET


NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col_to_idx(col):
    value = 0
    for char in col:
        if char.isalpha():
            value = value * 26 + (ord(char.upper()) - 64)
    return value - 1


def parse_xlsx_rows(file_bytes):
    with ZipFile(BytesIO(file_bytes)) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in root.findall("main:si", NS):
                shared_strings.append(
                    "".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
                )

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}

        first_sheet = workbook.find("main:sheets", NS)[0]
        rid = first_sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = rel_map[rid].lstrip("/")
        if not target.startswith("xl/"):
            target = f"xl/{target}"

        root = ET.fromstring(archive.read(target))
        sheet_data = root.find("main:sheetData", NS)
        rows = []

        for row in sheet_data.findall("main:row", NS):
            values = {}
            for cell in row.findall("main:c", NS):
                ref = cell.attrib.get("r", "")
                col = "".join(ch for ch in ref if ch.isalpha())
                idx = _col_to_idx(col)
                cell_type = cell.attrib.get("t")
                value_node = cell.find("main:v", NS)
                inline_node = cell.find("main:is", NS)
                value = ""
                if cell_type == "s" and value_node is not None:
                    raw = value_node.text or ""
                    value = shared_strings[int(raw)] if raw and int(raw) < len(shared_strings) else raw
                elif cell_type == "inlineStr" and inline_node is not None:
                    value = "".join(
                        t.text or "" for t in inline_node.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                    )
                elif value_node is not None:
                    value = value_node.text or ""
                values[idx] = value

            if values:
                ordered = [values.get(i, "") for i in range(max(values) + 1)]
                rows.append(ordered)

        if not rows:
            return []

        headers = [str(item).strip() for item in rows[0]]
        data_rows = []
        for row in rows[1:]:
            payload = {}
            for idx, header in enumerate(headers):
                if not header:
                    continue
                payload[header] = row[idx] if idx < len(row) else ""
            if any(str(value).strip() for value in payload.values()):
                data_rows.append(payload)

        return data_rows
