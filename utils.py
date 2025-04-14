import pandas as pd
from io import StringIO

def ensure_dict(obj):
    """
    If obj is not a dict but has a .dict() method (e.g. a pydantic model), convert it.
    Otherwise, raise a TypeError.
    """
    if isinstance(obj, dict):
        return obj
    elif hasattr(obj, "dict"):
        return obj.dict()
    else:
        raise TypeError("The provided object must be a dict or have a .dict() method.")
    
def extract_table_from_text(full_text: str) -> pd.DataFrame:
    lines = full_text.splitlines()
    table_lines = []
    in_table = False
    for line in lines:
        if line.strip().startswith("|"):
            in_table = True
            table_lines.append(line)
        else:
            if in_table:
                break

    if not table_lines:
        return pd.DataFrame()
    header_line = table_lines[0]
    data_lines = table_lines[2:] if len(table_lines) > 1 else []

    def parse_line(line: str):
        return [cell.strip() for cell in line.strip().strip("|").split("|")]
    
    headers = parse_line(header_line)
    data = [parse_line(line) for line in data_lines if line.strip()]
    df = pd.DataFrame(data, columns=headers)
    return df

import re
import pandas as pd

def extract_table_from_response(response):
    # Parse JSON-Antwort
    response_json = response.json()
    assistant_text = response_json["choices"][0]["message"]["content"]

    # Entferne den <think> ... </think> Abschnitt
    cleaned_text = re.sub(r'<think>.*?</think>', '', assistant_text, flags=re.DOTALL)

    # Splitte den Text in Zeilen
    lines = cleaned_text.splitlines()

    # Finde den Start der Tabelle (sucht nach einer Zeile, in der "|" und "Indikation" vorkommen)
    start_index = None
    for i, line in enumerate(lines):
        if "|" in line and "Indikation" in line:
            start_index = i
            break

    if start_index is None:
        print("Keine Tabelle gefunden.")
        return None

    # Finde das Ende der Tabelle – hier wird die nächste leere Zeile als Ende angenommen
    end_index = None
    for j in range(start_index, len(lines)):
        if lines[j].strip() == "":
            end_index = j
            break
    if end_index is None:
        end_index = len(lines)

    table_lines = lines[start_index:end_index]
    if len(table_lines) < 2:
        print("Tabelle ist zu kurz oder unvollständig.")
        return None

    header_line = table_lines[0]
    data_lines = table_lines[2:]  # Überspringe Header und Trennzeile

    # Hilfsfunktion: Parse eine Zeile in einzelne Zellen
    def parse_row(line):
        # Spalte anhand des Pipes – optionaler Whitespace
        cells = [cell.strip() for cell in re.split(r"\s*\|\s*", line.strip())]
        # Entferne erste und letzte Zelle, wenn diese leer sind (häufig wegen führendem oder endendem Pipe)
        if cells and cells[0] == '':
            cells = cells[1:]
        if cells and cells[-1] == '':
            cells = cells[:-1]
        return cells

    headers = parse_row(header_line)
    
    rows = []
    for line in data_lines:
        # Überspringe Trennzeilen oder leere Zeilen
        if line.strip().startswith("---") or not line.strip():
            continue
        row = parse_row(line)
        # Falls die Anzahl der Zellen in der Zeile nicht mit der Header-Anzahl übereinstimmt, zeige eine Warnung und überspringe die Zeile
        if len(row) != len(headers):
            print(f"Warnung: Anzahl der Zellen ({len(row)}) stimmt nicht mit Header ({len(headers)}) überein. Überspringe Zeile: {row}")
            continue
        rows.append(row)
    
    df = pd.DataFrame(rows, columns=headers)
    return df
