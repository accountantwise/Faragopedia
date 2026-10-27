"""Markdown table parsing, shared by every script that reads one (safeguard B1).

The 2026-10-26 incident: extracts escape a pipe inside a cell as `\\|` (role
"Y3 \\| SPOMA"), and five scripts each split rows with a plain `split("|")`. The
escaped pipe became an extra cell, every later column shifted by one, and the role
fragment was read as the person's name and the name as their company — 12 fake company
pages named after people, 18 junk contacts named after companies or roles, and ~80
people silently lost. So there is now exactly one splitter, and it is strict:

- cells are separated by UNESCAPED pipes only;
- a row whose cell count differs from its header raises MalformedRow. It is never
  re-aligned, padded or truncated, because a shifted row puts real values in the wrong
  fields without any visible error.
"""
from __future__ import annotations

import re

CELL_BOUNDARY = re.compile(r"(?<!\\)\|")
ESCAPED_PIPE = re.compile(r"\s*\\\|\s*")


class MalformedRow(ValueError):
    """A table row whose cell count doesn't match its header."""


def split_raw(line: str) -> list[str]:
    """Split on unescaped pipes, keeping the empty segments outside the outer pipes and
    every cell's original text, so `"|".join(split_raw(line)) == line`. For scripts that
    rewrite one cell of a live page and must leave the rest byte-for-byte."""
    return CELL_BOUNDARY.split(line)


def split_cells(line: str, unescape: bool = True) -> list[str]:
    """The cells of one table row, stripped, outer pipes removed. With unescape=True an
    escaped pipe inside a value is rendered as " / " so nothing downstream ever sees a
    pipe inside a value."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells = [c.strip() for c in CELL_BOUNDARY.split(s)]
    return [ESCAPED_PIPE.sub(" / ", c) for c in cells] if unescape else cells


def is_separator(cells: list[str]) -> bool:
    """A |---|:---:| rule row. Tested per cell: an earlier version asked whether the whole
    row's charset was a superset of {"-"} and silently dropped every hyphen-free row."""
    return bool(cells) and all(set(c) <= {"-", ":", " "} and c for c in cells)


def check_width(cells: list[str], width: int, where: str, line: str) -> None:
    if len(cells) != width:
        raise MalformedRow(f"{where}: row has {len(cells)} cells, header has {width}: {line.strip()[:160]}")


def read_table(lines: list[str], header_first_cell: str, where: str = "table",
               unescape: bool = True) -> tuple[list[str], list[list[str]]]:
    """Find the table whose header's first cell is `header_first_cell` (case-insensitive)
    and return (header, rows). Every row is width-checked against the header."""
    header: list[str] | None = None
    rows: list[list[str]] = []
    for line in lines:
        if not line.strip().startswith("|"):
            if header is not None:
                break
            continue
        cells = split_cells(line, unescape)
        if header is None:
            if cells and cells[0].lower() == header_first_cell.lower():
                header = cells
            continue
        if is_separator(cells):
            continue
        check_width(cells, len(header), where, line)
        rows.append(cells)
    if header is None:
        raise ValueError(f"{where}: no table with header starting '{header_first_cell}'")
    return header, rows
