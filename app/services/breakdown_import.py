from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile
from xml.etree import ElementTree as ET


NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

CANONICAL_BREAKDOWN_COLUMNS = [
    "PLAY #",
    "QTR",
    "SERIES",
    "DN",
    "DIST",
    "HASH",
    "YARD LN",
    "SIDE",
    "PLAY TYPE",
    "RESULT",
    "YDS",
    "FORMATION",
    "PERSONNEL",
    "MOTION",
    "PLAY DIR",
    "FRONT",
    "COVERAGE",
    "BLITZ",
    "PRESSURE",
    "SUMMARY",
    "CLIP #",
    "GAME",
    "FOCUS TEAM",
    "ANALYSIS MODE",
]

HEADER_ALIASES = {
    "PLAY#": "PLAY #",
    "PLAY NO": "PLAY #",
    "PLAY NUMBER": "PLAY #",
    "PLAY NUM": "PLAY #",
    "QUARTER": "QTR",
    "PERIOD": "QTR",
    "DRIVE": "SERIES",
    "POSSESSION": "SERIES",
    "DOWN": "DN",
    "DISTANCE": "DIST",
    "YARDLINE": "YARD LN",
    "FIELD POSITION": "YARD LN",
    "SIDE OF BALL": "SIDE",
    "PLAY_TYPE": "PLAY TYPE",
    "PLAYTYPE": "PLAY TYPE",
    "YARDS": "YDS",
    "YARDS GAINED": "YDS",
    "PLAY DIRECTION": "PLAY DIR",
    "DIRECTION": "PLAY DIR",
}


def _col_to_idx(col):
    value = 0
    for char in col:
        if char.isalpha():
            value = value * 26 + (ord(char.upper()) - 64)
    return value - 1


def _idx_to_col(idx):
    value = idx + 1
    chars = []
    while value:
        value, remainder = divmod(value - 1, 26)
        chars.append(chr(65 + remainder))
    return "".join(reversed(chars))


def _normalize_header(header):
    raw = str(header or "").strip()
    if not raw:
        return ""
    compact = " ".join(raw.replace("_", " ").split()).upper()
    return HEADER_ALIASES.get(compact, compact)


def normalize_breakdown_row(row):
    normalized = {}
    for header, value in (row or {}).items():
        key = _normalize_header(header)
        if not key:
            continue
        text_value = "" if value is None else str(value).strip()
        if key not in normalized or (not normalized[key] and text_value):
            normalized[key] = text_value
    return normalized


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
                data_rows.append(normalize_breakdown_row(payload))

        return data_rows


def build_breakdown_xlsx_bytes(rows, headers=None):
    headers = headers or CANONICAL_BREAKDOWN_COLUMNS
    workbook_rows = [headers] + [[row.get(header, "") for header in headers] for row in rows]

    sheet_rows_xml = []
    for row_idx, row_values in enumerate(workbook_rows, start=1):
        cells_xml = []
        for col_idx, raw_value in enumerate(row_values):
            cell_ref = f"{_idx_to_col(col_idx)}{row_idx}"
            if raw_value is None or raw_value == "":
                continue
            if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
                cells_xml.append(f'<c r="{cell_ref}"><v>{raw_value}</v></c>')
            else:
                text = escape(str(raw_value))
                cells_xml.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        sheet_rows_xml.append(f'<row r="{row_idx}">{"".join(cells_xml)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows_xml)}</sheetData>'
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Breakdown" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", root_rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()
