#!/usr/bin/env python3
"""Read the Tier2 QA sheet (xlsx download or per-tab CSV) with the standard library only."""

from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

TC_TAB = "01 TC정의"
ISSUE_TAB = "04 결함과결정"
AUTOMATION_TAB = "05 자동화매핑"


def _column_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - 64)
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.itertext()) for node in root.findall("m:si", NS)]


def _sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.get("Id"): rel.get("Target") for rel in rels.iter(f"{REL_NS}Relationship")}
    paths = {}
    for sheet in workbook.find("m:sheets", NS):
        rel_id = sheet.get(f"{{{NS['r']}}}id")
        target = targets[rel_id].lstrip("/")
        paths[sheet.get("name")] = target if target.startswith("xl/") else f"xl/{target}"
    return paths


def _cell_text(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(cell.find("m:is", NS).itertext())
    value = cell.find("m:v", NS)
    if value is None or value.text is None:
        return ""
    if kind == "s":
        return shared[int(value.text)]
    return value.text


def read_xlsx_tab(path: Path, tab: str) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        paths = _sheet_paths(archive)
        if tab not in paths:
            raise KeyError(f"'{tab}' 탭이 없습니다. 있는 탭: {', '.join(paths)}")
        shared = _shared_strings(archive)
        root = ET.fromstring(archive.read(paths[tab]))
    rows = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        values: list[str] = []
        for cell in row.findall("m:c", NS):
            index = _column_index(cell.get("r"))
            while len(values) < index:
                values.append("")
            values.append(_cell_text(cell, shared))
        rows.append(values)
    return rows


def read_csv(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [row for row in csv.reader(handle)]


def records(rows: list[list[str]]) -> list[dict[str, str]]:
    """Turn rows into dicts keyed by the header row, skipping blank rows."""
    if not rows:
        return []
    header = [name.strip() for name in rows[0]]
    result = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        padded = row + [""] * (len(header) - len(row))
        result.append({name: padded[i].strip() for i, name in enumerate(header) if name})
    return result


def load_tab(path: Path, tab: str) -> list[dict[str, str]]:
    if path.suffix.lower() == ".csv":
        return records(read_csv(path))
    return records(read_xlsx_tab(path, tab))
