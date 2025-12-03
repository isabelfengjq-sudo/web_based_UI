import io
import math
import re
from typing import Iterable, List, Sequence

import pandas as pd


def extract_codes_list(v: object, min_code: int = -500, max_code: int = 500) -> List[int]:
    """
    Return a list of integer codes found in v, preserving order and removing duplicates.

    Handles examples like:
      1
      "2;1"
      "1,2,3"
      "{_1,_2_3}"
      "[1 2 3]"
      (1, "2;3")
    """
    codes: List[int] = []

    def add_code(n: int) -> None:
        if n < min_code or n > max_code:
            return
        if n not in codes:
            codes.append(n)

    def handle_one(x: object) -> None:
        if x is None:
            return
        if isinstance(x, float) and math.isnan(x):
            return

        if isinstance(x, (int, float)) and not isinstance(x, bool):
            if isinstance(x, float) and not x.is_integer():
                return
            add_code(int(x))
            return

        for m in re.findall(r"-?\d+", str(x)):
            try:
                n = int(m)
            except ValueError:
                continue
            add_code(n)

    if isinstance(v, (list, tuple, set)):
        for item in v:
            handle_one(item)
    else:
        handle_one(v)

    return codes


def normalize_braced_value(val: object, min_code: int = -500, max_code: int = 500) -> object:
    """
    Convert strings like '{_3}' or '{_8,_2,_3}' to 3 or [8,2,3] respectively.
    Leaves everything else unchanged.
    """
    codes = extract_codes_list(val, min_code=min_code, max_code=max_code)
    if not codes:
        return val
    return codes[0] if len(codes) == 1 else codes


def numeric_like(series: pd.Series, pct_numeric: float = 0.9, minv: int = -500, maxv: int = 500) -> bool:
    """Heuristic to decide whether a column behaves like numeric codes."""
    s = pd.to_numeric(series, errors="coerce")
    return (s.notna().mean() >= pct_numeric) and (s.min(skipna=True) >= minv) and (s.max(skipna=True) <= maxv)


def excel_sheet_names(file_bytes: bytes) -> List[str]:
    """Return available sheet names from an Excel file provided as bytes."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    return xl.sheet_names


def read_excel_sheet(file_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    """Read a single sheet from Excel bytes."""
    return pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name)


def select_ids_from_df(
    df: pd.DataFrame,
    conditions: List[dict],
    respondent_col: str = "Respondent_Serial",
) -> List[int]:
    """
    Apply AND logic across per-column conditions and return respondent IDs.

    Supports ops:
      - eq: codes in cell must equal the single target code (no extras)
      - in: any overlap with selected codes
      - mc: selected codes are all present (may include extras)
      - nc: does not contain any selected codes
    """
    if respondent_col not in df.columns:
        raise KeyError(
            f"ID column '{respondent_col}' not found in df.columns.\n"
            f"Current columns: {list(df.columns)}"
        )

    def value_codes(v) -> set[int]:
        return set(extract_codes_list(v))

    mask = pd.Series(True, index=df.index)

    for cond in conditions:
        col = cond["column"]
        op = cond["op"]
        vals = cond["values"]

        if col not in df.columns:
            raise ValueError(f"Column not found: {col}")

        try:
            vals_set = {int(v) for v in vals}
        except Exception as exc:
            raise ValueError(f"Values must be integers: {vals}") from exc

        if op == "eq" and len(vals_set) != 1:
            raise ValueError("'eq' expects exactly one value.")
        if op not in ("eq", "in", "mc", "nc"):
            raise ValueError(f"Unsupported op: {op}")

        s = df[col]

        def row_match(v):
            codes = value_codes(v)
            if not codes:
                return False

            if op == "eq":
                target = next(iter(vals_set))
                return codes == {target}
            if op == "in":
                return bool(codes & vals_set)
            if op == "mc":
                return vals_set.issubset(codes)
            if op == "nc":
                return not bool(codes & vals_set)
            return False

        cond_mask = s.map(row_match)
        mask &= cond_mask

    out = df.loc[mask, respondent_col].dropna().drop_duplicates()
    try:
        return out.astype(int).tolist()
    except Exception:
        return out.astype(str).tolist()
