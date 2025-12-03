#!/usr/bin/env python
# coding: utf-8

# In[1]:


from IPython.display import HTML
HTML("""
<style>
.big-note{font-size:20px;line-height:1.55}
.big-note h1{font-size:36px;margin:0 0 .25rem 0}
.big-note h2{font-size:28px;margin:.4rem 0 .25rem 0}
.big-note .tip{background:#111; border:1px solid #444; padding:10px 12px; border-radius:8px}
.big-note .kbd{font-family:ui-monospace, SFMono-Regular, Menlo, monospace; background:#222; padding:.05rem .4rem; border-radius:4px}
</style>
""")


# <div class="big-note">
# <h1>Introduction of this Work Book</h1>
# There are 7 sections:
# <ul>
# <li>Rows = respondents whose IDs are in <span class="kbd">matched_ids_list</span></li>
# <li>Columns = <span class="kbd">Respondent_Serial</span> + your selected variables</li>
# </ul>
# You’ll see a preview; keep using <span class="kbd">final_table</span> for any downstream analysis or export.
# </div>

# <div class="big-note">
# <h1>Step 0 —Set up</h1>
# <div class="tip">
# • Make sure your Excel has a respondent ID column named <span class="kbd">Respondent_Serial</span>.<br>
# • Run the following cells frist for SETUPS. No need to understand the code below.
# </div>
# <strong>Key vars:</strong> <span class="kbd">df</span> (full dataset), <span class="kbd">RESP_COL = "Respondent_Serial"</span>
# </div>
# 

# In[2]:


# Step 0 — Set up environment and shared imports
import sys, platform, subprocess, jupyterlab_widgets, jupyterlab, openpyxl
import numpy as np, pandas as pd, ipywidgets as w
import matplotlib.pyplot as plt
import re
import math

from IPython.display import display, clear_output, HTML
from typing import List, Dict, Literal

# --- Install core packages (safe to re-run; will just upgrade if needed) ---
subprocess.check_call([sys.executable, "-m", "pip", "install", "-U",
                       "pip", "pandas", "openpyxl",
                       "ipywidgets>=8,<9", "jupyterlab_widgets>=3,<4"])


# <div class="big-note">
# <h1>Step 1 — Load data</h1>
# <div class="tip">
# • Upload your xlsx file in the block below.<br>
# • Copy and Paste the EXACT FILE NAME in ("file name") in the below sentence: "pd.ExcelFile("Copy of 25037102_DATA_修改第13版_0902(6).xlsx")".<br>
# • You NEED to update this variable every time you rename the xlsx or use a new file.  <br>
# • DOUBLE CHECK: Make sure your Excel has a respondent ID column named <span class="kbd">Respondent_Serial</span>.<br>
# • Then, run the cell below so that <span class="kbd">df</span> exists.
# </div>
# <strong>Key vars:</strong> <span class="kbd">df</span> (full dataset), <span class="kbd">RESP_COL = "Respondent_Serial"</span>
# </div>
# 

# In[3]:


xl = pd.ExcelFile("075691_rawdata_1124_v2 2.xlsx")
xl.sheet_names
df = pd.read_excel("075691_rawdata_1124_v2 2.xlsx", sheet_name=xl.sheet_names[0])
df.head()


# ## <div class="big-note">
# <h1>Just run the following</h1>

# In[4]:


def select_ids_from_df(df, conditions, respondent_col="Respondent_Serial", atol=None):
    mask = pd.Series(True, index=df.index)
    for i, cond in enumerate(conditions, 1):
        col = cond["column"]; op = cond["op"]; vals = cond["values"]
        if col not in df.columns:
            raise ValueError(f"[cond {i}] column not found: {col}")

        s = pd.to_numeric(df[col], errors="coerce")
        valid = s.notna() & (s >= -500) & (s <= 500)

        if op == "eq":
            if not (isinstance(vals, (list, tuple)) and len(vals) == 1):
                raise ValueError(f"[cond {i}] 'eq' expects a single value in 'values'.")
            target = float(vals[0])
            if atol is None:
                cond_mask = valid & (s == target)
            else:
                cond_mask = valid & np.isclose(s, target, rtol=0, atol=atol)

        elif op == "in":
            targets = [float(v) for v in vals]
            if atol is None:
                cond_mask = valid & s.isin(targets)
            else:
                # match any target within tolerance
                m = False
                for t in targets:
                    m = m | np.isclose(s, t, rtol=0, atol=atol)
                cond_mask = valid & m
        else:
            raise ValueError(f"[cond {i}] unsupported op: {op!r}")

        mask &= cond_mask

    out = df.loc[mask, respondent_col].dropna().drop_duplicates()
    try:
        return out.astype(int).tolist()   # keep your respondent IDs numeric if possible
    except Exception:
        return out.astype(str).tolist()


# In[5]:


###AND logic across columns
conditions = [
    {"column": "Qu_1", "op": "eq", "values": [1]},
    {"column": "Qu_2", "op": "in", "values": [2, 3]},
    # add more like {"column":"Qu_5","op":"eq","values":[0]},
]


# <div class="big-note">
# <h1>Step 2 — Pick columns to filter</h1>

# In[6]:


# Step 2 — show instructions in output
step2_instructions = """
<div class="note">
<h1>Step 2 — Pick columns to filter</h1>
Use the column picker to choose the variables you want to filter on (e.g., <span class="kbd">Qu_1</span>, <span class="kbd">S2_Province</span>, …).<br>
This sets <span class="kbd">selected_columns</span> for the next step.<br>
First, select how many columns you want, then press "Return".<br> 
Next, select the column name.<br>
You can type the column name in the blank space for faster picks.<br>
If you do not find the column you want, please check the box for "Show ALL columns".<br>
SUGGSTION: ALWAYS CHECK THIS BOX.<br>
Then, click "Confirm Selection".<br>
After this, scrow down and go the step 3. DO NOT re-run this step, or you will need to select your columns again.
</div>
"""

display(HTML(step2_instructions))
RESP_COL = "Respondent_Serial"  # excluded from choices
PLACEHOLDER = ("— pick a column —", None)

# --- universal code parser using regex ---
def extract_codes_list(v, min_code=-500, max_code=500):
    """
    Return a list of integer codes found in v, preserving order
    and removing duplicates.

    Handles, for example:
      1
      "1"
      "2;1"
      "1,2,3"
      "{_1,_2_3}"
      "[1, 2, 3]"
      "(1 2 3)"
      "1:2:3"
      "10^20-30"
      [1, "2;3"]

    If no valid codes are found, returns [].
    """
    codes: list[int] = []

    def add_code(n: int):
        if n < min_code or n > max_code:
            return
        if n not in codes:
            codes.append(n)

    def handle_one(x):
        # skip explicit missing values
        if x is None:
            return
        if isinstance(x, float) and math.isnan(x):
            return

        # numeric scalars: keep integer-like values as-is
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            if isinstance(x, float) and not x.is_integer():
                return
            add_code(int(x))
            return

        # everything else: treat as string and regex out digit groups
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

# ----- candidate columns -----
all_cols = [c for c in df.columns if c != RESP_COL]

def numeric_like(col, pct_numeric=0.9, minv=-500, maxv=500):
    s = pd.to_numeric(df[col], errors="coerce")
    return (s.notna().mean() >= pct_numeric) and (s.min(skipna=True) >= minv) and (s.max(skipna=True) <= maxv)

numeric_candidates = [c for c in all_cols if numeric_like(c)]

def _normalize_braced_value(val):
    """
    Convert strings like:
      '{_3}'           -> 3
      '{_8,_2,_3,_5}'  -> [8, 2, 3, 5]
    Leave everything else unchanged.
    """
    codes = extract_codes_list(val)
    if not codes:
        return val
    return codes[0] if len(codes) == 1 else codes


# ----- widgets -----
show_all = w.Checkbox(value=False, description="Show ALL columns")
k_input  = w.BoundedIntText(value=1, min=1, max=len(all_cols), description="How many?")
container = w.VBox()                 # holds the dropdowns
confirm_btn = w.Button(description="Confirm selection", button_style="primary", icon="check")
reset_btn   = w.Button(description="Reset", icon="refresh")
msg = w.HTML("")
out = w.Output()

# state
_dds = []               # dropdowns
selected_columns = []   # final picks after confirm
_updating = False       # event-suppression flag

def current_base():
    return (numeric_candidates if not show_all.value else all_cols)

def _allowed_options(current_value, forbidden):
    """Return [(label,value), ...] with placeholder and base minus forbidden (except current)."""
    base = current_base()
    allowed = [c for c in base if (c not in forbidden) or (c == current_value)]
    return [PLACEHOLDER] + [(c, c) for c in allowed]

def _on_dd_change(change=None):
    # rebuild options for each dropdown without triggering loops
    global _updating
    if _updating: 
        return
    _updating = True
    chosen = [dd.value for dd in _dds]                 # values (may include None)
    for i, dd in enumerate(_dds):
        other_forbidden = set(chosen) - {dd.value, None}
        prev = dd.value
        dd.options = _allowed_options(prev, other_forbidden)
        # keep previous value if still allowed; otherwise reset to placeholder
        allowed_vals = {v for _, v in dd.options}
        dd.value = prev if prev in allowed_vals else None
    _updating = False

    filled = sum(v is not None for v in chosen)
    msg.value = f"<b>Selected:</b> {filled}/{len(_dds)}"

def build_dropdowns(k):
    """Create K dropdowns with placeholders; no auto-selection."""
    global _dds
    _dds = []
    for i in range(k):
        dd = w.Dropdown(
            options=_allowed_options(None, set()),
            description=f"Col #{i+1}",
            value=None,
            layout=w.Layout(width="360px")
        )
        dd.observe(_on_dd_change, names="value")
        _dds.append(dd)
    container.children = _dds
    _on_dd_change()  # initial render + status

def on_k_change(change):
    build_dropdowns(k_input.value)

def on_show_all_change(change):
    _on_dd_change()

def on_reset_clicked(b):
    build_dropdowns(k_input.value)
    with out:
        clear_output()

def on_confirm_clicked(b):
    global selected_columns
    cols = [dd.value for dd in _dds]
    if any(v is None for v in cols):
        msg.value = "<span style='color:#c00'>Please pick a column in every slot.</span>"
        return
    if len(set(cols)) != len(cols):
        msg.value = "<span style='color:#c00'>Duplicate columns detected—pick unique columns.</span>"
        return

    # Step 2: save the chosen columns
    selected_columns = cols

    # Step 2.5 — normalize values like '{_3}' or '{_8,_2,_3,_5}'
    for col in selected_columns:
        df[col] = df[col].map(_normalize_braced_value)

    msg.value = "<span style='color:#070'>✅ Columns selected & Step 2.5 normalization done.</span>"
    with out:
        clear_output()
        print("Columns:", selected_columns)
        print("Step 2.5: normalized values like '{_3}' and '{_8,_2,_3,_5}'.")
        print("Next: define per-column conditions (eq / in {…}) and run the filter.")


# init
k_input.observe(on_k_change, names="value")
show_all.observe(on_show_all_change, names="value")
confirm_btn.on_click(on_confirm_clicked)
reset_btn.on_click(on_reset_clicked)

display(w.VBox([
    w.HTML("<b>Step 2.1 — Define the number of column(s)</b>"),
    w.HBox([k_input, show_all]),
    w.HTML("<b>Step 2.2 — Define the filter condition(s)</b>"),
    container,
    w.HBox([confirm_btn, reset_btn]),
    msg,
    out
]))


build_dropdowns(k_input.value)


# <div class="big-note">
# <h1>Step 3 — Define rules &amp; run filter</h1>

# In[15]:


step3_instructions = """
<div class="note">
<h1>Step 3 — Define rules &amp; run filter</h1>

<p>For each column you selected in Step 2, choose an operator and then pick the code(s) you want to keep.</p>

<ul>
  <li><b>Equals (=)</b>: keep rows where the cell is exactly that single code.<br>
      For multi-choice questions, the cell must contain <i>only</i> this one code.</li>

  <li><b>In set (any of)</b>: keep rows where <i>any</i> of the selected codes appear in the cell.</li>

  <li><b>MCQ: Contains all</b>: for multi-choice questions, keep rows where the response includes 
      <i>every</i> selected code (it may also contain extra codes).</li>

  <li><b>MCQ: Does not contain</b>: keep rows where the response does <i>not</i> contain 
      <i>any</i> of the selected codes.</li>
</ul>

<p><b>Important when using “In set” for ranges</b></p>
<ul>
  <li>If you want a continuous range from A to B, you must tick <i>every</i> code between A and B.</li>
  <li>Example: to select 1–5, tick 1, 2, 3, 4, 5.<br>
      If you only tick 1 and 5, you will only get rows with values 1 or 5.</li>
</ul>

<p>Then click <b>Run filter</b>. The notebook will:</p>
<ol>
  <li>Apply all rules together with logical AND (a row must satisfy <i>every</i> rule).</li>
  <li>Show a one-column table of matched IDs as 
      <span class="kbd">output1_ids_df</span>.</li>
  <li>In the helper cell below, this column will be converted into 
      <span class="kbd">matched_ids_list</span> for later steps.</li>
</ol>

<p>If you want to start over, click <b>Clear selections</b> to reset all operators and choices.</p>
<p>After clicking Run filter, please go to step 4. Do not re-run this step, or you will have to pick the filters again.</p>
</div>
"""
display(HTML(step3_instructions))
# --- safety checks ---
if "df" not in globals():
    raise RuntimeError("DataFrame `df` not found. Load your Excel first.")
if "selected_columns" not in globals() or not selected_columns:
    raise RuntimeError("`selected_columns` is empty. Run the column picker cell first.")

# >>> if your ID column isn't EXACTLY this, change here <<<
RESP_COL = "Respondent_Serial"

# holders for results you can use later
output1_ids: list[int] = []
output1_ids_df = pd.DataFrame(columns=[RESP_COL])

def allowed_vals(col):
    """
    Collect all numeric codes used in this column, handling both scalar and multi-coded cells.
    Example cell values after Step 2.5: 3, [3, 2, 5], etc.
    """
    vals = set()
    for v in df[col].dropna():
        if isinstance(v, (list, tuple, set)):
            items = v
        else:
            items = [v]

        for x in items:
            try:
                x_int = int(x)
            except (TypeError, ValueError):
                continue
            if -100 <= x_int <= 100:
                vals.add(x_int)

    if not vals:
        return list(range(-100, 100))
    return sorted(vals)


# ---- build per-column condition widgets ----
col_ui = {}
rows   = []

for col in selected_columns:
    op = w.ToggleButtons(
        options=[
            ("Equals (=)", "eq"),
            ("In set (any of)", "in"),
            ("MCQ: Contains all", "mc"),
            ("MCQ: Does not contain", "nc")
        ],
        value="eq",
        description=col,
        button_style=""
    )
    vals   = allowed_vals(col)
    eq_dd  = w.Dropdown(options=vals, description="=")
    in_sel = w.SelectMultiple(options=vals, description="in { }", 
                              rows=min(6, max(3, len(vals))))
    box = w.VBox([op, eq_dd])

    def _switch(change, _col=col):
        b = col_ui[_col]["box"]
        if col_ui[_col]["op"].value == "eq":
            b.children = [col_ui[_col]["op"], col_ui[_col]["eq"]]
        else:
            b.children = [col_ui[_col]["op"], col_ui[_col]["in"]]

    op.observe(_switch, names="value")
    col_ui[col] = {"op": op, "eq": eq_dd, "in": in_sel, "box": box}
    rows.append(box)

run_btn   = w.Button(description="Run filter", button_style="primary", icon="play")
clear_btn = w.Button(description="Clear selections", icon="trash")
out       = w.Output()

# ---- selector function with eq / in (ANY) / mc (ALL) ----
from typing import List, Dict, Literal
Op = Literal["eq", "in", "mc","nc"]

def select_ids_from_df(
    df: pd.DataFrame,
    conditions: List[Dict[str, object]],
    respondent_col: str = RESP_COL,
):
    if respondent_col not in df.columns:
        raise KeyError(
            f"ID column '{respondent_col}' not found in df.columns.\n"
            f"Current columns: {list(df.columns)}"
        )

    def value_codes(v) -> set[int]:
        return set(extract_codes_list(v))
    

    # Start with "all rows allowed"
    mask = pd.Series(True, index=df.index)

    for i, cond in enumerate(conditions, 1):
        col = cond["column"]; op: Op = cond["op"]; vals = cond["values"]

        if col not in df.columns:
            raise ValueError(f"[cond {i}] column not found: {col}")

        # normalize selected values into a set of ints
        try:
            vals_set = {int(v) for v in vals}
        except Exception:
            raise ValueError(f"[cond {i}] values must be integers: {vals}")

        if op not in ("eq", "in", "mc", "nc"):
            raise ValueError(f"[cond {i}] unsupported op: {op}")

        # For "Equals", we expect a single value
        if op == "eq" and len(vals_set) != 1:
            raise ValueError(
                f"[cond {i}] 'Equals' expects exactly one value. "
                f"Use 'In set' or 'Multiple choice' for multiple values."
            )

        s = df[col]

        def row_match(v):
            codes = value_codes(v)
            if not codes:
                return False

            if op == "eq":
                # Equals: exact code for single-coded questions.
                # Single-valued cell: 3 with selected 3 -> match
                # Multi-coded cell: [3,2] with selected 3 -> NO match
                target = next(iter(vals_set))
                return codes == {target}

            elif op == "in":
                # In set (ANY): match if there is ANY overlap
                # Example: selected {2, 3}
                #   cell {3}        -> match
                #   cell {2, 3}     -> match
                #   cell {4}        -> no match
                return bool(codes & vals_set)

            elif op == "mc":
                # Multiple choice (ALL): match only if ALL selected are present
                # Example: selected {2, 3}
                #   cell {3}        -> no match
                #   cell {2}        -> no match
                #   cell {2, 3}     -> match
                #   cell {2, 3, 5}  -> match
                return vals_set.issubset(codes)
                
            elif op == "nc":
                # Does not contain: keep only rows that do NOT contain
                # ANY of the selected codes.
                # Selected {1}:
                #   cell {1}           -> False (drop)
                #   cell {1, 3}        -> False (drop)
                #   cell {2, 3}        -> True  (keep)
                # Selected {1, 2}:
                #   cell {1}           -> False
                #   cell {2}           -> False
                #   cell {1, 2, 3}     -> False
                #   cell {3, 4}        -> True
                return not bool(codes & vals_set)

        cond_mask = s.map(row_match)
        # AND logic across columns: apply each condition on top of previous ones
        mask &= cond_mask

    out = df.loc[mask, respondent_col].dropna().drop_duplicates()
    try:
        return out.astype(int).tolist()
    except Exception:
        return out.astype(str).tolist()


# ---- actions ----
def on_run(_):
    with out:
        clear_output()
        # build conditions from UI
        conditions = []
        for col, ui in col_ui.items():
            op = ui["op"].value  # "eq", "in", "mc", or "nc"

            if op == "eq":
                v = ui["eq"].value
                if v is None:
                    print(f"Please pick a value for {col}.")
                    return
                conditions.append({
                    "column": col,
                    "op": "eq",
                    "values": [int(v)],
                })

            elif op in ("in", "mc", "nc"):
                vals = list(ui["in"].value)
                if not vals:
                    print(f"Please pick one or more values for {col}.")
                    return
                conditions.append({
                    "column": col,
                    "op": op,  # keep "in" vs "mc" vs "nc"
                    "values": [int(x) for x in vals],
                })

        # run filter
        ids = select_ids_from_df(df, conditions, respondent_col=RESP_COL)

        global output1_ids, output1_ids_df
        output1_ids = ids
        output1_ids_df = pd.DataFrame({RESP_COL: output1_ids})

        print("Conditions:", conditions)
        print(f"Matched: {len(output1_ids)} respondents")
        display(output1_ids_df)

def on_clear(_):
    for ui in col_ui.values():
        ui["op"].value = "eq"

run_btn.on_click(on_run)
clear_btn.on_click(on_clear)

display(w.VBox([
    w.HTML("<b>Step 3 — Define conditions for each selected column</b>"),
    w.HBox([run_btn, clear_btn]),
    w.VBox(rows),
    out
]))


# In[16]:


RESP_COL = "Respondent_Serial"
# replace `output1_ids_df` with whatever variable holds the Step 3 table
matched_ids_list = pd.to_numeric(output1_ids_df.iloc[:, 0], errors="coerce").dropna().astype(int).tolist()
print(*matched_ids_list)


# <div class="big-note">
# <h1>Step 4 — Choose columns to add &amp; build table</h1>

# In[20]:


step4_instructions = """
<div class="note">
<h1>Step 4 — Choose columns to add &amp; build table</h1>
Select the columns you want to further inspect.(They will be added <i>beside</i> the matched IDs).  
Click <b>Build table</b> to create <span class="kbd">raw_table</span>:
<ul>
<li>Rows = respondents whose IDs are in <span class="kbd">matched_ids_list</span></li>
<li>Columns = <span class="kbd">Respondent_Serial</span> + your selected variables</li>
</ul>
You’ll see a preview; keep using <span class="kbd">raw_table</span> for any downstream analysis. After you see the table, go on to step 5.1, 5.2, or 5.3 per your needs.
</div>
"""
display(HTML(step4_instructions))
# --- safety checks ---
if "df" not in globals():
    raise RuntimeError("DataFrame `df` not found. Load your Excel first.")
if "matched_ids_list" not in globals() or not matched_ids_list:
    raise RuntimeError("No IDs from Step 3. Run Step 3 first.")
if "RESP_COL" not in globals():
    raise RuntimeError("`RESP_COL` not defined. Define it (e.g. 'Respondent_Serial') before Step 4.")

# --- column picker: user chooses which columns to include in the table ---
_all_cols = [c for c in df.columns if c != RESP_COL]

cols_picker = w.SelectMultiple(
    options=_all_cols,
    description="Columns",
    rows=min(14, len(_all_cols))
)

build_btn = w.Button(description="Build raw table", button_style="primary", icon="table")
clear_btn = w.Button(description="Clear selection", icon="trash")
out4 = w.Output()

def _build_raw_table(_):
    with out4:
        clear_output()

        chosen = list(cols_picker.value)
        if not chosen:
            print("Pick at least one column to include in the table.")
            return

        # 1) subset df to only the matched IDs from Step 3
        base = df[df[RESP_COL].isin(matched_ids_list)].copy()

        # 2) keep Step 3 order using matched_ids_list as the row order
        left = pd.DataFrame({RESP_COL: matched_ids_list})
        right = base[[RESP_COL] + chosen].copy()
        # make sure merge key is numeric-compatible if possible
        right[RESP_COL] = pd.to_numeric(right[RESP_COL], errors="coerce")

        raw = left.merge(right, on=RESP_COL, how="left")

        # 3) expose as `raw_table` and preview
        globals()["raw_table"] = raw

        print(f"raw_table built: {len(raw)} rows × {raw.shape[1]} columns")
        display(raw.head(30))

def _clear_selection(_):
    cols_picker.value = tuple()
    with out4:
        clear_output()
        print("Column selection cleared.")

build_btn.on_click(_build_raw_table)
clear_btn.on_click(_clear_selection)

display(w.VBox([
    w.HTML("<b>Step 4 — Choose columns to build the raw table for matched IDs</b>"),
    cols_picker,
    w.HBox([build_btn, clear_btn]),
    out4
]))


# <div class="big-note">
# <h1>Step 5.1 — Filter raw_table BY COLUMN</h1>

# In[22]:


step5_instructions = """
<div class="note">
<h1>Step 5.1 — Filter <code>raw_table</code> by column</h1>

<p>This step lets you slice <span class="kbd">raw_table</span> by column values. 
For each column, you can choose an operator and the code(s) you want to keep or remove.</p>

<p><b>For each column</b>, pick one of the operators:</p>
<ul>
  <li><b>Equals</b>: keep rows where the response contains this single code.<br>
      Works for both single-choice and multi-choice columns.</li>

  <li><b>In set (ANY)</b>: keep rows where <i>any</i> of the selected codes appear in the cell.</li>

  <li><b>Multiple choice (ALL)</b>: for multi-choice questions, keep rows where the response includes 
      <i>all</i> selected codes (it can also contain extra codes).</li>

  <li><b>Does not contain</b>: keep rows where the response does <i>not</i> contain 
      <i>any</i> of the selected codes.</li>
</ul>

<p><b>Tips</b>:</p>
<ul>
  <li>If you leave the selection empty for a column, that column is <i>not</i> used as a filter.</li>
  <li>For multi-choice questions, the tool automatically reads codes inside formats like 
      <code>{_1,_2,_3}</code>, <code>1,2,3</code>, or <code>1;2;3</code>.</li>
</ul>

<p>When you click <b>Run filter on raw_table</b>, the notebook will:</p>
<ol>
  <li>Start from the full <span class="kbd">raw_table</span>.</li>
  <li>Apply all active column rules together using logical AND 
      (a row must satisfy <i>every</i> rule to be kept).</li>
  <li>Create <span class="kbd">filtered_table</span> containing the remaining rows 
      and show the first 30 rows as a preview.</li>
</ol>

<p><b>Important:</b> <span class="kbd">raw_table</span> is never changed in this step. 
You can safely re-run the filters as many times as you like.</p>

<p>If you want to start over, click <b>Clear filters</b> to reset all operators and selections.</p>
</div>
"""
display(HTML(step5_instructions))
# --- safety checks ---
if "raw_table" not in globals():
    raise RuntimeError("`raw_table` not found. Run Step 4 first.")
if "RESP_COL" not in globals():
    RESP_COL = "Respondent_Serial"  # fallback if not set

# if RESP_COL is missing for some reason, just treat first column as ID
if RESP_COL not in raw_table.columns:
    RESP_COL = raw_table.columns[0]

# columns you can filter on (exclude ID by default)
filter_cols = [c for c in raw_table.columns if c != RESP_COL]

cols_info = w.HTML(
    "<b>Columns in raw_table:</b> " + ", ".join(map(str, raw_table.columns))
)

# --- helpers to handle multi-choice values like '{_9,_2,_3}' ---
def _value_codes(v):
    """
    Shared parser for Step 5.1 filters.

    Examples:
        3, "3"         -> {3}
        "2;1"          -> {1, 2}
        "1,2,3"        -> {1, 2, 3}
        "{_1,_2_3}"    -> {1, 2, 3}
        "[1 2 3]"      -> {1, 2, 3}
        (1, "2;3")     -> {1, 2, 3}
    """
    return set(extract_codes_list(v))


def _allowed_vals(col):
    vals = set()
    for v in raw_table[col].dropna():
        for x in _value_codes(v):
            vals.add(x)
    return sorted(vals) if vals else list(range(-100, 100))


# --- build per-column filter widgets ---
col_ui = {}
rows   = []

for col in filter_cols:
    op = w.ToggleButtons(
        options=[
            ("Equals", "eq"),
            ("In set (ANY)", "in"),
            ("Multiple choice (ALL)", "mc"),
            ("Does not contain", "nc"),
        ],
        value="in",
        description=col,
        button_style="",
    )
    vals   = _allowed_vals(col)
    eq_dd  = w.Dropdown(options=vals, description="=")
    in_sel = w.SelectMultiple(options=vals, description="in { }",
                              rows=min(6, max(3, len(vals))))

    box = w.VBox([op, in_sel])  # default UI is "in"

    def _switch(change, _col=col):
        b = col_ui[_col]["box"]
        if col_ui[_col]["op"].value == "eq":
            b.children = [col_ui[_col]["op"], col_ui[_col]["eq"]]
        else:
            b.children = [col_ui[_col]["op"], col_ui[_col]["in"]]

    op.observe(_switch, names="value")
    col_ui[col] = {"op": op, "eq": eq_dd, "in": in_sel, "box": box}
    rows.append(box)

run_btn   = w.Button(description="Run filter on raw_table", button_style="primary", icon="play")
clear_btn = w.Button(description="Clear filters", icon="trash")
out5      = w.Output()


def _run_filter(_):
    with out5:
        clear_output()

        # start from the entire raw_table
        base = raw_table.copy()

        for col, ui in col_ui.items():
            if col not in base.columns:
                print(f"Skipping filter for '{col}' (not in current table).")
                continue

            op = ui["op"].value  # "eq", "in", "mc", or "nc"

            # Equals: single value; interpret as "contains this code"
            if op == "eq":
                v = ui["eq"].value
                if v is None:
                    continue
                target = int(v)

                def _row_match_eq(val):
                    codes = _value_codes(val)
                    if not codes:
                        return False
                    # CONTAINS target code (so it works for multi-choice too)
                    return target in codes

                base = base[base[col].map(_row_match_eq)]

            # In / MC / NC: use the multi-select widget
            elif op in ("in", "mc", "nc"):
                vals = list(ui["in"].value)
                if not vals:
                    # empty selection = no filter for this column
                    continue
                vals_set = {int(x) for x in vals}

                def _row_match_multi(val):
                    codes = _value_codes(val)
                    if not codes:
                        return False

                    if op == "in":
                        # ANY overlap
                        return bool(codes & vals_set)
                    elif op == "mc":
                        # ALL selected present
                        return vals_set.issubset(codes)
                    elif op == "nc":
                        # DOES NOT CONTAIN any selected codes
                        return not bool(codes & vals_set)

                base = base[base[col].map(_row_match_multi)]

        # keep existing row order; no index gymnastics with RESP_COL
        filtered = base.copy()

        globals()["filtered_table"] = filtered

        print(f"filtered_table built: {len(filtered)} rows × {filtered.shape[1]} columns")
        display(filtered.head(30))


def _clear_filters(_):
    for ui in col_ui.values():
        ui["op"].value = "in"
        ui["in"].value = tuple()
    with out5:
        clear_output()
        print("Filters cleared. raw_table is unchanged.")

run_btn.on_click(_run_filter)
clear_btn.on_click(_clear_filters)

display(w.VBox([
    cols_info,
    w.VBox(rows),
    w.HBox([run_btn, clear_btn]),
    out5
]))


# In[23]:


# Step 5.1.1 — Append extra columns to filtered_table (quota columns)
if "df" not in globals():
    raise RuntimeError("No df found. Please run Step 1 first.")

if "filtered_table" not in globals():
    raise RuntimeError("No filtered_table found. Please run Step 5.1 first.")

ft = filtered_table.copy()

id_col = RESP_COL if RESP_COL in ft.columns else ft.columns[0]

# Columns that are available in df but not yet in filtered_table
available_cols = [c for c in df.columns if c != id_col and c not in ft.columns]

if not available_cols:
    print("No additional columns in df that are not already in filtered_table.")
    print("You can still proceed to Step 5.1.2 if you already have quota columns inside filtered_table.")
else:
    big_note = w.HTML(
        "<div class='note'>"
        "<h3>Step 5.1.1 — Append extra columns to filtered_table (quota columns)</h3>"
        "<p>Select extra columns from the original df to add into <code>filtered_table</code>. "
        "These will be treated as potential <b>quota columns</b> in Step 5.1.2.</p>"
        "</div>"
    )

    cols_picker = w.SelectMultiple(
        options=available_cols,
        description="Extra cols",
        rows=min(14, len(available_cols)),
        layout=w.Layout(width="50%")
    )

    apply_button = w.Button(
        description="Append to filtered_table",
        button_style="success",
        layout=w.Layout(width="50%")
    )

    out = w.Output()

    def on_apply_clicked(_):
        with out:
            clear_output()
            selected = list(cols_picker.value)
            if not selected:
                print("No columns selected. Nothing changed.")
                return

            # Merge original df columns onto filtered_table
            add_cols = [id_col] + selected
            merged = ft.merge(
                df[add_cols].drop_duplicates(subset=id_col),
                on=id_col,
                how="left",
                suffixes=("", "_from_df")
            )

            # Update globals
            global filtered_table, filtered_quota_cols
            filtered_table = merged
            filtered_quota_cols = selected

            print(f"Appended {len(selected)} column(s) to filtered_table:")
            for c in selected:
                print("  -", c)
            print("\nNew filtered_table shape:", filtered_table.shape)
            print("Stored as potential quota columns in filtered_quota_cols.")

    apply_button.on_click(on_apply_clicked)

    ui = w.VBox([big_note, cols_picker, apply_button, out])
    display(ui)


# In[24]:


# Step 5.1.2 — Customize bins for quota columns (no change to filtered_table)
# --- safety checks ---
if "filtered_table" not in globals():
    raise RuntimeError("No filtered_table found. Please run Step 5.1 first.")

base_ft = filtered_table  # original, NEVER modified here

id_col = RESP_COL if RESP_COL in base_ft.columns else base_ft.columns[0]

# working copy that will carry binned values
# IMPORTANT: always reset to the *current* filtered_table
ft_bt = base_ft.copy()
globals()["filtered_table_with_bins"] = ft_bt

# determine which columns are quota columns (those added in 5.1.1)
if "filtered_quota_cols" in globals():
    quota_cols = [c for c in globals()["filtered_quota_cols"] if c in base_ft.columns]
else:
    # fallback: treat non-0/1 columns as quota columns
    candidate_cols = [c for c in base_ft.columns if c != id_col]
    quota_cols = []
    for c in candidate_cols:
        vals = set(base_ft[c].dropna().unique())
        if vals - {0, 1}:
            quota_cols.append(c)

if not quota_cols:
    raise RuntimeError(
        "No quota columns found. Please add extra columns in Step 5.1.1 first."
    )

# --- UI widgets ---

col_dd = w.Dropdown(
    options=quota_cols,
    description="Quota col:"
)

customize_toggle = w.Checkbox(
    value=False,
    description="Enable custom bins editing"
)

num_bins_box = w.BoundedIntText(
    value=2,
    min=1,
    max=10,
    description="# bins:"
)

bins_box = w.VBox([])           # will hold Bin 1 / Bin 2 / ...
apply_btn = w.Button(
    description="Apply bins to column",
    button_style="warning",
    disabled=True
)
comb_btn = w.Button(
    description="Recalculate combinations",
    button_style="success"
)
out = w.Output()

bin_selects = []   # list[SelectMultiple] for current column


def _current_codes_for_col(col: str):
    """Extract all integer codes present in the ORIGINAL filtered_table column."""
    vals_raw = base_ft[col].dropna().unique()
    codes = set()
    for v in vals_raw:
        for code in extract_codes_list(v):
            codes.add(code)
    return sorted(codes)


def _build_bins_ui(*_):
    """Rebuild bin selectors when column or #bins changes."""
    global bin_selects

    col = col_dd.value
    if not col:
        bins_box.children = [w.Label("No column selected.")]
        return

    codes = _current_codes_for_col(col)
    if not codes:
        bins_box.children = [w.Label("No numeric codes found in this column.")]
        return

    num_bins_box.max = len(codes)
    if num_bins_box.value > len(codes):
        num_bins_box.value = len(codes)

    selects = []
    for i in range(num_bins_box.value):
        sel = w.SelectMultiple(
            options=codes,
            description=f"Bin {i+1}",
            rows=min(6, len(codes)),
            disabled=not customize_toggle.value
        )
        selects.append(sel)

    bin_selects = selects
    bins_box.children = selects


def _toggle_enable(change):
    """Enable / disable bin selectors + apply button."""
    enabled = change["new"]
    for sel in bin_selects:
        sel.disabled = not enabled
    apply_btn.disabled = not enabled


def _apply_bins(_btn):
    """Apply user-defined bins to the selected column in filtered_table_with_bins."""
    global ft_bt
    with out:
        clear_output()

        col = col_dd.value
        if not col:
            print("No column selected.")
            return

        if not bin_selects:
            print("Please set the number of bins first.")
            return

        # gather bin specs
        bins = [set(sel.value) for sel in bin_selects if sel.value]
        if not bins:
            print("Please select values for each bin.")
            return

        # check for overlaps
        used = set()
        for i, b in enumerate(bins):
            if used & b:
                print(
                    f"Error: overlapping values between bins. "
                    f"Check Bin {i+1}."
                )
                return
            used |= b

        if not used:
            print("No codes specified in bins.")
            return

        # build mapping value -> bin index (1,2,...)
        code_to_bin = {}
        for idx, b in enumerate(bins, start=1):
            for code in b:
                code_to_bin[int(code)] = idx

        def map_to_bin(v):
            codes = extract_codes_list(v)
            for c in codes:
                if c in code_to_bin:
                    return code_to_bin[c]
            return np.nan

        # apply mapping on ORIGINAL column values, write into ft_bt
        new_col = base_ft[col].map(map_to_bin).astype("Int64")
        ft_bt[col] = new_col
        globals()["filtered_table_with_bins"] = ft_bt

        print(
            f"Applied {len(bins)} bins to column '{col}' in filtered_table_with_bins. "
            f"New unique values in that column: "
            f"{sorted(ft_bt[col].dropna().unique().tolist())}"
        )


def _recalc_combos(_btn):
    """Compute #bins per quota column and total combinations (using binned table)."""
    with out:
        clear_output()

        info = {}
        total = 1
        for c in quota_cols:
            n_bins = int(ft_bt[c].dropna().nunique())
            info[c] = n_bins
            if n_bins > 0:
                total *= n_bins

        globals()["filtered_quota_bins_info"] = info
        globals()["filtered_quota_total_combinations"] = int(total)

        print("Number of bins per quota column (from filtered_table_with_bins):")
        for c, n in info.items():
            print(f"  {c}: {n}")
        print(f"\nTotal number of combinations: {total}")


# wire up events
col_dd.observe(_build_bins_ui, names="value")
num_bins_box.observe(_build_bins_ui, names="value")
customize_toggle.observe(_toggle_enable, names="value")
apply_btn.on_click(_apply_bins)
comb_btn.on_click(_recalc_combos)

# initial UI build
_build_bins_ui()

display(w.VBox([
    w.HTML(
        "<h3>Step 5.1.2 — Customize bins for quota columns (filtered_table_with_bins)</h3>"
        "<p>Original <code>filtered_table</code> is kept intact."
        "<br/>Bins are applied only to <code>filtered_table_with_bins</code>."
        "<br/>Click <b>Recalculate combinations</b> to see how many "
        "bin combinations exist across all quota columns.</p>"
    ),
    w.Label(f"Quota columns: {', '.join(quota_cols)}"),
    col_dd,
    customize_toggle,
    num_bins_box,
    bins_box,
    w.HBox([apply_btn, comb_btn]),
    out
]))


# In[25]:


# Step 5.1.3 — Randomly sample respondents from each bin combination
# --- safety checks ---
if "filtered_table_with_bins" not in globals():
    raise RuntimeError(
        "No filtered_table_with_bins found. Please run Step 5.1.2 first."
    )

if "filtered_quota_bins_info" not in globals() or not filtered_quota_bins_info:
    raise RuntimeError(
        "No filtered_quota_bins_info found. Please run Step 5.1.2 and "
        "click 'Recalculate combinations' first."
    )

ft_bt = filtered_table_with_bins.copy()

id_col = RESP_COL if RESP_COL in ft_bt.columns else ft_bt.columns[0]

# quota columns we actually use (those with bins defined and present in table)
quota_cols = [c for c in filtered_quota_bins_info.keys() if c in ft_bt.columns]

if not quota_cols:
    raise RuntimeError(
        "No valid quota columns found in filtered_table_with_bins.\n"
        "Make sure Step 5.1.2 has applied bins to at least one column."
    )

# rows where all quota-bin values are present
working = ft_bt.dropna(subset=quota_cols).copy()

if working.empty:
    raise RuntimeError(
        "No rows have complete bin values across all quota columns.\n"
        "Check your binning in Step 5.1.2 (some columns may still have NaNs)."
    )

# build combination labels as a tuple of bin values
working["__combo__"] = list(zip(*(working[c] for c in quota_cols)))
combo_counts = working["__combo__"].value_counts().sort_index()

# theoretical combinations (from Step 5.1.2)
theoretical_combos = 1
for c, n_bins in filtered_quota_bins_info.items():
    if n_bins > 0:
        theoretical_combos *= n_bins
    # if 0 bins, skip (no contribution)

# --- UI ---

big_note = w.HTML(
    "<div class='note'>"
    "<h3>Step 5.1.3 — Randomly sample respondents from each bin combination</h3>"
    "<p>You are now working on <code>filtered_table_with_bins</code>, using the quota "
    "bins defined in Step 5.1.2.<br/>"
    "Each unique combination of quota-bin values across the selected quota columns "
    "is treated as one <b>bin</b> (combination).</p>"
    "<p>For each bin combination, this step will randomly select the requested number "
    "of respondents. The results are stored in "
    "<code>selected_rows_from_filtered_bins</code> and "
    "<code>selected_ids_from_filtered_bins</code>.</p>"
    "</div>"
)

info_html = w.HTML(
    f"<p><b>Quota columns:</b> {', '.join(quota_cols)}<br/>"
    f"<b>Theoretical combinations (from bins):</b> {theoretical_combos}<br/>"
    f"<b>Observed combinations in data:</b> {combo_counts.size}</p>"
)

sample_per_combo_input = w.BoundedIntText(
    value=1,
    min=1,
    max=1000,
    description="Sample per bin:",
    layout=w.Layout(width="50%")
)

run_button = w.Button(
    description="Sample respondents",
    button_style="success",
    layout=w.Layout(width="50%")
)

out = w.Output()

def _make_bin_label(row):
    parts = []
    for c in quota_cols:
        v = row[c]
        if pd.notna(v):
            # v is an Int64 bin index; display as "BinX"
            try:
                parts.append(f"{c}=Bin{int(v)}")
            except Exception:
                parts.append(f"{c}={v}")
    return ", ".join(parts)

def on_run_clicked(_):
    global selected_rows_from_filtered_bins, selected_ids_from_filtered_bins

    with out:
        clear_output()

        k = int(sample_per_combo_input.value)
        if k < 1:
            print("Sample size per bin must be at least 1.")
            return

        groups = working.groupby("__combo__", dropna=False)

        sampled_rows = []
        warnings = []

        for combo_val, grp in groups:
            n_avail = len(grp)
            if n_avail == 0:
                continue

            if n_avail < k:
                warnings.append(
                    f"Bin {combo_val} has only {n_avail} respondents; "
                    f"sampling all {n_avail} instead of {k}."
                )
                n_to_sample = n_avail
            else:
                n_to_sample = k

            sampled = grp.sample(n=n_to_sample, replace=False, random_state=None)
            sampled_rows.append(sampled)

        if not sampled_rows:
            print("No respondents found in any bin combination.")
            return

        result = pd.concat(sampled_rows, ignore_index=True)

        # create a human-readable bin label per respondent
        result["Bin_Label"] = result.apply(_make_bin_label, axis=1)

        # store globals
        selected_rows_from_filtered_bins = result
        selected_ids_from_filtered_bins = result[id_col].tolist()

        # --- output / documentation ---

        print("Sampling complete.")
        print(f"Requested per-bin sample size: {k}")
        print(f"Number of observed bin combinations: {combo_counts.size}")
        print(f"Total respondents selected: {len(selected_ids_from_filtered_bins)}\n")

        if warnings:
            print("Warnings:")
            for wmsg in warnings:
                print("  -", wmsg)
            print()

        print("Preview of selected respondents with their bin labels:")
        display(
            result[[id_col, "Bin_Label"] + quota_cols]
            .sort_values(quota_cols + [id_col])
            .head(20)
        )

        print("\nYou can inspect the full selection in "
              "`selected_rows_from_filtered_bins` "
              "(includes all columns from filtered_table_with_bins).")

        print("\nIf you just need the respondent IDs (one per line), "
              "they are stored in `selected_ids_from_filtered_bins`.\n")
        print("IDs (one per line, copy-paste friendly):")
        print("\n".join(str(x) for x in selected_ids_from_filtered_bins))

run_button.on_click(on_run_clicked)

ui = w.VBox([
    big_note,
    info_html,
    sample_per_combo_input,
    run_button,
    out
])

display(ui)


# <div class="big-note">
# <h1>Step 5.2 — Row-based calculation on raw_table(intended for Mention Rate)</h1>

# In[29]:


# Step 5.2 — Row-based calculation & manipulation on raw_table
step5_2_instructions = """
<div class="note">
<h1>Step 5.2 — Row-based calculation on <code>raw_table</code> (Mention Rate)</h1>

<p>This step calculates, for <b>each respondent</b>, how often a specific code (or set of codes) is mentioned 
across all data columns in <span class="kbd">raw_table</span>.  
The result is an average "mention rate" between 0 and 1.</p>

<p><b>How it works</b>:</p>
<ul>
  <li>We use <b>all non-ID columns</b> in <span class="kbd">raw_table</span> as the calculation base.</li>
  <li>For each row (respondent), we check every column and see if it matches your chosen rule.</li>
  <li>We then compute: <code>Average = (number of matching columns) / (total number of columns)</code>.</li>
</ul>

<p><b>Step 1 — Choose a mode</b></p>
<ul>
  <li><b>Equals (single code)</b>: counts a column as a hit if the response 
      contains this specific code.</li>
  <li><b>In set (ANY of selected)</b>: counts a column as a hit if 
      <i>any</i> of the selected codes appear in that cell.</li>
  <li><b>Multiple choice (ALL selected)</b>: counts a column as a hit only if 
      the cell includes <i>all</i> the selected codes (it may also contain extras).</li>
</ul>

<p><b>Step 2 — Pick code(s)</b></p>
<ul>
  <li>For <b>Equals</b>, pick <b>one</b> code in the dropdown.</li>
  <li>For <b>In set</b> or <b>Multiple choice (ALL)</b>, pick one or more codes in the multi-select list.</li>
  <li>The tool automatically parses formats like <code>{_1,_2,_3}</code>, <code>1,2,3</code>, <code>1;2;3</code>, etc.</li>
</ul>

<p>Click <b>Run row-based calc</b>. The notebook will:</p>
<ol>
  <li>Loop over each respondent in <span class="kbd">raw_table</span>.</li>
  <li>Count how many columns match your chosen rule.</li>
  <li>Compute an average mention rate for each respondent.</li>
  <li>Create <span class="kbd">avg_num_of_times</span> with two columns:
    <ul>
      <li><span class="kbd">RESP_COL</span> (respondent ID)</li>
      <li><span class="kbd">Average</span> (mention rate, 0–1)</li>
    </ul>
  </li>
  <li>Show the first 30 rows as a preview.</li>
</ol>
</div>
"""
display(HTML(step5_2_instructions))
# --- safety checks ---
if "raw_table" not in globals():
    raise RuntimeError("`raw_table` not found. Run Step 4 first.")
if "RESP_COL" not in globals():
    RESP_COL = "Respondent_Serial"

if RESP_COL not in raw_table.columns:
    # fallback: treat first column as ID if RESP_COL is missing
    RESP_COL = raw_table.columns[0]

data_cols = [c for c in raw_table.columns if c != RESP_COL]
if not data_cols:
    raise RuntimeError("raw_table has no data columns (only ID). Add some columns in Step 4 first.")

# --- helper: parse codes from cells (same spirit as Step 5) ---
def _value_codes(v):
    """
    Shared parser for Step 6 row-based calc.

    Handles all encodings like:
        3, "3"
        "2;1"
        "1,2,3"
        "{_1,_2_3}"
        "[1 2 3]"
        (1, "2;3")
    """
    return set(extract_codes_list(v))


# --- find all possible codes across the selected columns ---
all_codes = set()
for col in data_cols:
    for v in raw_table[col].dropna():
        for x in _value_codes(v):
            all_codes.add(x)

codes_list = sorted(all_codes) if all_codes else list(range(-100, 100))

# --- UI: choose mode + desired value(s) ---
mode = w.ToggleButtons(
    options=[
        ("Equals (single code)", "eq"),
        ("In set (ANY of selected)", "in"),
        ("Multiple choice (ALL selected)", "mc"),
    ],
    value="eq",
    description="Mode",
)

eq_dd  = w.Dropdown(options=codes_list, description="Code")
in_sel = w.SelectMultiple(options=codes_list, description="Codes",
                          rows=min(6, max(3, len(codes_list))))

choice_box = w.VBox([])

def _switch_mode(change=None):
    if mode.value == "eq":
        choice_box.children = [eq_dd]
    else:
        choice_box.children = [in_sel]

_switch_mode()
mode.observe(_switch_mode, names="value")

run_btn   = w.Button(description="Run row-based calc", button_style="primary", icon="play")
clear_btn = w.Button(description="Clear selection", icon="trash")
out6      = w.Output()

def _run_row_calc(_):
    with out6:
        clear_output()

        op = mode.value  # "eq", "in", or "mc"

        # get selected codes
        if op == "eq":
            v = eq_dd.value
            if v is None:
                print("Please pick a code for 'Equals'.")
                return
            target = int(v)
            vals_set = {target}
        else:
            vals = list(in_sel.value)
            if not vals:
                print("Please pick one or more codes.")
                return
            vals_set = {int(x) for x in vals}
            target = None  # not used

        n_cols = len(data_cols)
        ids = []
        avgs = []

        # loop over respondents (rows)
        for _, row in raw_table.iterrows():
            rid = row[RESP_COL]
            hits = 0

            for col in data_cols:
                codes = _value_codes(row[col])
                if not codes:
                    continue  # counts as 0 for this column

                if op == "eq":
                    match = (target in codes)
                elif op == "in":
                    match = bool(codes & vals_set)        # ANY
                elif op == "mc":
                    match = vals_set.issubset(codes)      # ALL
                else:
                    match = False

                if match:
                    hits += 1

            avg = hits / n_cols if n_cols > 0 else float("nan")
            ids.append(rid)
            avgs.append(avg)

        avg_df = pd.DataFrame({
            RESP_COL: ids,
            "Average": avgs,
        })

        globals()["avg_num_of_times"] = avg_df

        print(f"avg_num_of_times built: {len(avg_df)} rows × 2 columns")
        display(avg_df.head(30))

def _clear_codes(_):
    eq_dd.value = None if len(eq_dd.options) else None
    in_sel.value = tuple()
    with out6:
        clear_output()
        print("Selection cleared. raw_table is unchanged.")

run_btn.on_click(_run_row_calc)
clear_btn.on_click(_clear_codes)

display(w.VBox([
    w.HTML(
        f"Using {len(data_cols)} columns: " + ", ".join(map(str, data_cols))
    ),
    mode,
    choice_box,
    w.HBox([run_btn, clear_btn]),
    out6
]))


# <div class="big-note">
# <h1>Step 5.2.1— Distribution and Visualization</h1>

# In[31]:


step5_2_1_instructions = """
<div class="note">
<h1>Step 5.2.1— Distribution and Visualization</h1>
<p>In <b>Step 5.2.1</b>, we will take <span class="kbd">avg_num_of_times</span> and:</p>
<ul>
  <li>Visualize the distribution of these averages, and</li>
  <li>Split respondents into 4 bins (e.g., Top 25%, Upper middle 25%, Lower middle 25%, Bottom 25%) 
      and build a table showing which respondent falls into which bin.</li>
</ul>

<p><b>Note:</b> <span class="kbd">raw_table</span> is never modified here.  
You can change the mode/codes and re-run the calculation as many times as you like.</p>

<p>If you want to start over, click <b>Clear selection</b> to reset the chosen code(s).</p>
</div>
"""
display(HTML(step5_2_1_instructions))

# --- safety check ---
if "avg_num_of_times" not in globals():
    raise RuntimeError("`avg_num_of_times` not found. Run Step 6 first.")

# 1) Compute quartiles (for info / plotting)
q = avg_num_of_times["Average"].quantile([0.25, 0.5, 0.75])
q1, q2, q3 = q[0.25], q[0.5], q[0.75]

print("Quartile cut points (by value):")
print(f"Q1 (25%):  {q1:.4f}")
print(f"Q2 (50%):  {q2:.4f}")
print(f"Q3 (75%):  {q3:.4f}")

# 2) Assign each respondent to a bin using percentile *ranks*
bin_labels = ["Bottom 25%", "25–50%", "50–75%", "Top 25%"]

# percentile rank of each Average between 0 and 1
ranks = avg_num_of_times["Average"].rank(method="average", pct=True)

avg_num_of_times["Bin"] = pd.cut(
    ranks,
    bins=[0, 0.25, 0.5, 0.75, 1],
    labels=bin_labels,
    include_lowest=True,
)

# Table: which respondent is in which bin
avg_bins = avg_num_of_times[["Respondent_Serial", "Average", "Bin"]].copy()
globals()["avg_bins"] = avg_bins  # save for later use

print("\nRespondent bin assignment (first 30 rows):")
display(avg_bins.head(30))

# Optional: summary counts per bin
print("\nCounts per bin:")
display(avg_bins["Bin"].value_counts().reindex(bin_labels))

# 3) Visualization: histogram with quartile lines
plt.figure(figsize=(6, 4))
plt.hist(avg_num_of_times["Average"], bins=20)
plt.axvline(q1, linestyle="--")
plt.axvline(q2, linestyle="--")
plt.axvline(q3, linestyle="--")
plt.xlabel("Average")
plt.ylabel("Number of respondents")
plt.title("Distribution of Average (with quartile cut points)")
plt.show()
# Get all respondent IDs in the Bottom 25% bin
bottom_25_ids = avg_bins.loc[
    avg_bins["Bin"] == "Bottom 25%", "Respondent_Serial"
].tolist()

# If you prefer to hang it off a dict keyed by the label:
bin_id_lists = {
    "Bottom 25%": bottom_25_ids
}

print(f"Total in Bottom 25%: {len(bottom_25_ids)}")
  # this will show the full list
print(*bottom_25_ids)


# <div class="big-note">
# <h1>Step 5.3— 0/1 Matrix for initial inspection</h1>

# In[40]:


step5_3_instructions = """
<div class="note">
<h1>Step 5.3 — 0/1 matrix for initial inspection</h1>

<p>This step turns <span class="kbd">raw_table</span> into a simple 0/1 matrix for the code(s) you care about.</p>

<ul>
  <li>Select one or more <b>Code(s)</b> from the list.</li>
  <li>For each cell in <span class="kbd">raw_table</span>, we check whether it contains <b>all</b> selected codes.</li>
  <li>If it does, the cell becomes <b>1</b>; otherwise it becomes <b>0</b> (empty / non-code cells are also 0).</li>
</ul>

<p>Click <b>Create inspected_table</b> to build <span class="kbd">inspected_table</span>:</p>
<ul>
  <li>Rows = all respondents in <span class="kbd">raw_table</span></li>
  <li>Columns = ID column (<span class="kbd">{id_col}</span>) + all data columns converted to 0/1</li>
</ul>

<p>You’ll see a preview; later Step 5.3.x will use <span class="kbd">inspected_table</span> for binning, sampling, and further checks.</p>
</div>
"""
display(HTML(step5_3_instructions))

# --- safety checks ---
if "raw_table" not in globals():
    raise RuntimeError("No raw_table found. Please run Step 4 first.")

rt = raw_table.copy()

# determine ID and data columns
id_col = RESP_COL if RESP_COL in rt.columns else rt.columns[0]
data_cols = [c for c in rt.columns if c != id_col]

if not data_cols:
    raise RuntimeError("raw_table has no data columns besides the respondent ID.")

# --- collect all codes in raw_table to offer as choices ---
all_codes = set()
for col in data_cols:
    for v in rt[col].dropna():
        for code in extract_codes_list(v):  # uses the regex-based helper from Step 2
            all_codes.add(code)

codes_list = sorted(all_codes) if all_codes else list(range(-100, 101))

# --- UI: pick desired code(s), mc logic (ALL selected must be present) ---
desired_codes_sel = w.SelectMultiple(
    options=codes_list,
    description="Code(s)",
    rows=min(12, len(codes_list)),
    disabled=False
)

run_btn = w.Button(
    description="Create inspected_table",
    button_style="success"
)

out = w.Output()

def _cell_flag(v, target_set: set[int]) -> int:
    """
    Return 1 if the cell contains ALL codes in target_set (mc logic),
    otherwise 0. Empty / non-code cells -> 0.
    """
    codes = set(extract_codes_list(v))
    if not codes:
        return 0
    return 1 if target_set.issubset(codes) else 0

def _run_inspection(_btn):
    with out:
        clear_output()
        if not desired_codes_sel.value:
            print("Please select at least one code.")
            return

        target_set = set(int(x) for x in desired_codes_sel.value)

        inspected = rt.copy()
        for col in data_cols:
            inspected[col] = inspected[col].map(lambda v: _cell_flag(v, target_set))

        globals()["inspected_table"] = inspected

        print(f"inspected_table created with shape {inspected.shape}. "
              f"ID column: '{id_col}'.")
        display(inspected.head(30))

run_btn.on_click(_run_inspection)

display(w.VBox([
    w.HTML("<p>Select one or more codes. A cell is marked <b>1</b> if it "
           "contains <b>all</b> selected codes (mc logic); otherwise <b>0</b>.</p>"),
    desired_codes_sel,
    run_btn,
    out
]))


# In[41]:


# Step 5.3.1 — Append extra columns to inspected_table
# --- safety checks ---
if "inspected_table" not in globals():
    raise RuntimeError("No inspected_table found. Please run Step 5.3 first.")

if "df" not in globals():
    raise RuntimeError("No original df found. Please run Step 1/2 to load data first.")

it = inspected_table.copy()

# determine ID column
id_col = RESP_COL if RESP_COL in it.columns else it.columns[0]

# all candidate columns from the original df (excluding ID)
all_candidate_cols = [c for c in df.columns if c != id_col]

# only offer columns that are NOT already in inspected_table
available_extra_cols = [c for c in all_candidate_cols if c not in it.columns]

if not available_extra_cols:
    print("All columns from the original dataframe are already in inspected_table.")
else:
    cols_picker = w.SelectMultiple(
        options=available_extra_cols,
        description="Extra cols",
        rows=min(14, len(available_extra_cols))
    )

    add_btn = w.Button(
        description="Add to inspected_table",
        button_style="info"
    )

    out2 = w.Output()
    
    def _add_columns(_btn):
        with out2:
            clear_output()
            chosen = list(cols_picker.value)
            if not chosen:
                print("Please select at least one column to add.")
                return

            # take original values for those columns from df
            # only for the respondents present in inspected_table
            base = df[df[id_col].isin(it[id_col])][[id_col] + chosen].copy()

            # make sure order matches inspected_table rows
            base = (
                base.drop_duplicates(subset=id_col)
                    .set_index(id_col)
                    .reindex(it[id_col])
                    .reset_index()
            )

            # merge and keep original column order, with new ones appended
            merged = it.merge(base, on=id_col, how="left", suffixes=("", "_extra"))

            old_cols = list(it.columns)
            new_cols = [c for c in merged.columns if c not in old_cols]

            merged = merged[old_cols + new_cols]

            # track which columns are added as quota columns
            quota_cols = globals().get("inspected_quota_cols", [])
            for c in new_cols:
                if c not in quota_cols:
                    quota_cols.append(c)
            globals()["inspected_quota_cols"] = quota_cols

            globals()["inspected_table"] = merged

            print(
                f"inspected_table updated. New shape: {merged.shape}. "
                f"Added columns: {new_cols}"
            )
            display(merged.head(30))

    add_btn.on_click(_add_columns)

    display(w.VBox([
        w.HTML("<h3>Step 5.3.1 — Add extra columns to inspected_table</h3>"
               "<p>Select additional columns from the original data to append "
               "to the right of the current 0/1 matrix.</p>"),
        cols_picker,
        add_btn,
        out2
    ]))


# In[42]:


# Step 5.3.2 — Customize bins for quota columns (no change to inspected_table)

# --- safety checks ---
if "inspected_table" not in globals():
    raise RuntimeError("No inspected_table found. Please run Step 5.3 first.")

base_it = inspected_table  # original, NEVER modified here

id_col = RESP_COL if RESP_COL in base_it.columns else base_it.columns[0]

# working copy that will carry binned values
# IMPORTANT: always reset to the *current* inspected_table
bt = base_it.copy()
globals()["inspected_table_with_bins"] = bt


bt = base_it.copy()
globals()["inspected_table_with_bins"] = bt

# determine which columns are quota columns (those added in 5.4)
if "inspected_quota_cols" in globals():
    quota_cols = [c for c in globals()["inspected_quota_cols"] if c in base_it.columns]
else:
    # fallback: treat non-0/1 columns as quota columns
    candidate_cols = [c for c in base_it.columns if c != id_col]
    quota_cols = []
    for c in candidate_cols:
        vals = set(base_it[c].dropna().unique())
        if vals - {0, 1}:
            quota_cols.append(c)

if not quota_cols:
    raise RuntimeError(
        "No quota columns found. Please add extra columns in Step 5.4 first."
    )

# --- UI widgets ---

col_dd = w.Dropdown(
    options=quota_cols,
    description="Quota col:"
)

customize_toggle = w.Checkbox(
    value=False,
    description="Enable custom bins editing"
)

num_bins_box = w.BoundedIntText(
    value=2,
    min=1,
    max=10,
    description="# bins:"
)

bins_box = w.VBox([])           # will hold Bin 1 / Bin 2 / ...
apply_btn = w.Button(
    description="Apply bins to column",
    button_style="warning",
    disabled=True
)
comb_btn = w.Button(
    description="Recalculate combinations",
    button_style="success"
)
out = w.Output()

bin_selects = []   # list[SelectMultiple] for current column


def _current_codes_for_col(col: str):
    """Extract all integer codes present in the ORIGINAL inspected_table column."""
    vals_raw = base_it[col].dropna().unique()
    codes = set()
    for v in vals_raw:
        for code in extract_codes_list(v):
            codes.add(code)
    return sorted(codes)


def _build_bins_ui(*_):
    """Rebuild bin selectors when column or #bins changes."""
    global bin_selects

    col = col_dd.value
    if not col:
        bins_box.children = [w.Label("No column selected.")]
        return

    codes = _current_codes_for_col(col)
    if not codes:
        bins_box.children = [w.Label("No numeric codes found in this column.")]
        return

    num_bins_box.max = len(codes)
    if num_bins_box.value > len(codes):
        num_bins_box.value = len(codes)

    selects = []
    for i in range(num_bins_box.value):
        sel = w.SelectMultiple(
            options=codes,
            description=f"Bin {i+1}",
            rows=min(6, len(codes)),
            disabled=not customize_toggle.value
        )
        selects.append(sel)

    bin_selects = selects
    bins_box.children = selects


def _toggle_enable(change):
    """Enable / disable bin selectors + apply button."""
    enabled = change["new"]
    for sel in bin_selects:
        sel.disabled = not enabled
    apply_btn.disabled = not enabled


def _apply_bins(_btn):
    """Apply user-defined bins to the selected column in inspected_table_with_bins."""
    global bt
    with out:
        clear_output()

        col = col_dd.value
        if not col:
            print("No column selected.")
            return

        if not bin_selects:
            print("Please set the number of bins first.")
            return

        # gather bin specs
        bins = [set(sel.value) for sel in bin_selects if sel.value]
        if not bins:
            print("Please select values for each bin.")
            return

        # check for overlaps
        used = set()
        for i, b in enumerate(bins):
            if used & b:
                print(
                    f"Error: overlapping values between bins. "
                    f"Check Bin {i+1}."
                )
                return
            used |= b

        if not used:
            print("No codes specified in bins.")
            return

        # build mapping value -> bin index (1,2,...)
        code_to_bin = {}
        for idx, b in enumerate(bins, start=1):
            for code in b:
                code_to_bin[int(code)] = idx

        def map_to_bin(v):
            codes = extract_codes_list(v)
            for c in codes:
                if c in code_to_bin:
                    return code_to_bin[c]
            return np.nan

        # apply mapping on ORIGINAL column values, write into bt
        new_col = base_it[col].map(map_to_bin).astype("Int64")
        bt[col] = new_col
        globals()["inspected_table_with_bins"] = bt

        print(
            f"Applied {len(bins)} bins to column '{col}' in inspected_table_with_bins. "
            f"New unique values in that column: "
            f"{sorted(bt[col].dropna().unique().tolist())}"
        )


def _recalc_combos(_btn):
    """Compute #bins per quota column and total combinations (using binned table)."""
    with out:
        clear_output()

        info = {}
        total = 1
        for c in quota_cols:
            n_bins = int(bt[c].dropna().nunique())
            info[c] = n_bins
            if n_bins > 0:
                total *= n_bins

        globals()["quota_bins_info"] = info
        globals()["quota_total_combinations"] = int(total)

        print("Number of bins per quota column (from inspected_table_with_bins):")
        for c, n in info.items():
            print(f"  {c}: {n}")
        print(f"\nTotal number of combinations: {total}")


# wire up events
col_dd.observe(_build_bins_ui, names="value")
num_bins_box.observe(_build_bins_ui, names="value")
customize_toggle.observe(_toggle_enable, names="value")
apply_btn.on_click(_apply_bins)
comb_btn.on_click(_recalc_combos)

# initial UI build
_build_bins_ui()

display(w.VBox([
    w.HTML(
        "<h3>Step 5.3.2 — Customize bins for quota columns (inspected_table_with_bins)</h3>"
        "<p>Original <code>inspected_table</code> is kept intact."
        "<br/>Bins are applied only to <code>inspected_table_with_bins</code>."
        "<br/>Click <b>Recalculate combinations</b> to see how many "
        "bin combinations exist across all quota columns.</p>"
    ),
    w.Label(f"Quota columns: {', '.join(quota_cols)}"),
    col_dd,
    customize_toggle,
    num_bins_box,
    bins_box,
    w.HBox([apply_btn, comb_btn]),
    out
]))


# In[31]:


inspected_table_with_bins


# In[43]:


# Step 5.3.3 — Find combination of rows with target 0/1 sums AND even quota-bin distribution

# --- safety checks & table choice ---

if "inspected_table" not in globals():
    raise RuntimeError("No inspected_table found. Please create it first.")

# base 0/1 table
base_tbl = inspected_table.copy()

# use binned table if available (for quotas), else fall back to base_tbl
if "inspected_table_with_bins" in globals():
    tbl = inspected_table_with_bins.copy()
else:
    tbl = base_tbl.copy()

# identify ID column
id_col = RESP_COL if RESP_COL in tbl.columns else tbl.columns[0]

# identify quota columns (those added in Step 5.4 / binned in 5.3.2)
if "inspected_quota_cols" in globals():
    quota_cols = [c for c in globals()["inspected_quota_cols"] if c in tbl.columns]
else:
    quota_cols = []

# 0/1 columns are from inspected_table, excluding ID and quota columns
data_cols = [
    c for c in base_tbl.columns
    if c != id_col and c not in quota_cols
]

if not data_cols:
    raise RuntimeError(
        "No 0/1 data columns found for solving. "
        "Make sure inspected_table has non-quota columns."
    )

# ensure 0/1 integers on those columns (using base_tbl)
base_tbl[data_cols] = base_tbl[data_cols].fillna(0).astype(int)

# make sure tbl contains the same 0/1 values on those columns
for c in data_cols:
    tbl[c] = base_tbl[c]

# --- UI: row count (k) + target vector per data column ---

row_count_input = w.IntText(
    value=20,
    description="Rows (k):",
    min=1
)

target_inputs = {
    col: w.IntText(value=0, description=col) for col in data_cols
}

run_btn = w.Button(
    description="Find rows",
    button_style="primary"
)

out = w.Output()


def _ensure_pulp():
    """Import pulp, installing it via pip if needed."""
    try:
        import pulp  # noqa: F401
        return
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pulp"])
        import pulp  # noqa: F401


def _run_solve(_btn):
    with out:
        clear_output()

        k = row_count_input.value
        if k <= 0:
            print("Row count k must be positive.")
            return

        # target vector in column order
        targets = [target_inputs[c].value for c in data_cols]

        print("Solving for:")
        print(f"  k = {k} rows")
        print(f"  targets (0/1 cols) = {targets}")
        print(f"  using table: {'inspected_table_with_bins' if 'inspected_table_with_bins' in globals() else 'inspected_table'}")

        # --- build combination labels from quota columns (if any) ---

        if quota_cols:
            # each row's combination = tuple of its bin values across quota_cols
            combo_df = tbl[quota_cols].copy()
            combos = combo_df.apply(lambda row: tuple(row.tolist()), axis=1)

            # list of unique combinations, preserve order of appearance
            seen = {}
            combo_labels = []
            for idx, c in enumerate(combos):
                if c not in seen:
                    seen[c] = len(seen)
                    combo_labels.append(c)

            num_combos = len(combo_labels)

            if num_combos == 0:
                print("Warning: no valid combinations found from quota columns; "
                      "falling back to original solver without quota constraints.")
                use_quota = False
            else:
                use_quota = True
                if k % num_combos != 0:
                    print(f"Error: k = {k} is not divisible by number of combinations "
                          f"({num_combos}). Please adjust k.")
                    return

                per_combo = k // num_combos
                print(f"Detected {num_combos} distinct combinations from quota columns:")
                print(f"  quota columns: {quota_cols}")
                print(f"  rows per combination required: {per_combo}")

                # build mapping combo -> row indices
                combo_to_rows = {c: [] for c in combo_labels}
                for i, c in enumerate(combos):
                    combo_to_rows[c].append(i)

                # quick feasibility check: each combo must have enough rows
                for c in combo_labels:
                    if len(combo_to_rows[c]) < per_combo:
                        print(f"Error: combination {c} has only "
                              f"{len(combo_to_rows[c])} available rows, "
                              f"but {per_combo} are required.")
                        return
        else:
            use_quota = False
            print("No quota columns detected; running original solver without "
                  "even-distribution constraints.")

        # ensure pulp is available
        _ensure_pulp()
        import pulp

        A = base_tbl[data_cols].to_numpy(dtype=int)
        n_rows, n_cols = A.shape

        # --- build ILP ---
        prob = pulp.LpProblem("RowSelection", pulp.LpMinimize)

        # one binary variable per row: x_i = 1 if row i is selected
        x_vars = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n_rows)]

        # dummy objective (we just want *any* feasible solution)
        prob += 0

        # constraint: pick exactly k rows
        prob += pulp.lpSum(x_vars) == k

        # constraints: column sums must match targets (0/1 matrix)
        for j in range(n_cols):
            prob += pulp.lpSum(A[i, j] * x_vars[i] for i in range(n_rows)) == targets[j]

        # quota constraints: even distribution across combinations
        if use_quota:
            for c in combo_labels:
                rows_in_c = combo_to_rows[c]
                prob += pulp.lpSum(x_vars[i] for i in rows_in_c) == per_combo

        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))

        if pulp.LpStatus[status] != "Optimal":
            print("No exact solution found that satisfies all constraints.")
            print("Status:", pulp.LpStatus[status])
            return

        # extract chosen rows
        selected_idx = [i for i in range(n_rows) if pulp.value(x_vars[i]) > 0.5]

        print(f"\nFound a solution using {len(selected_idx)} rows.")

        sel_tbl = tbl.iloc[selected_idx].reset_index(drop=True)

        # store globally for later use
        globals()["selected_rows_from_inspected"] = sel_tbl
        globals()["selected_ids_from_inspected"] = sel_tbl[id_col].tolist()

        print("\nSelected respondent IDs:")
        print(sel_tbl[id_col].tolist())

        print("\nCheck: column sums of the selected rows (0/1 part):")
        print(sel_tbl[data_cols].sum(axis=0).tolist())

        if quota_cols:
            print("\nCheck: quota-bin combinations among selected rows:")
            print(sel_tbl[quota_cols].value_counts().sort_index())

        display(sel_tbl.head(30))


run_btn.on_click(_run_solve)

display(w.VBox(
    [w.HTML(
        "<h3>Step Y — Choose rows whose 0/1 sums match target vector "
        "with even quota-bin distribution</h3>"
        "<p>Targets are applied on the 0/1 columns from <code>inspected_table</code>."
        "<br/>If <code>inspected_table_with_bins</code> and quota columns exist, "
        "the solver will also enforce an equal number of selected rows from "
        "each quota-bin combination.</p>"
    )]
    + [row_count_input]
    + list(target_inputs.values())
    + [run_btn, out]
))


# In[37]:


print("\n".join(str(x) for x in selected_ids_from_inspected))


# In[35]:


selected_rows_from_inspected.head()

