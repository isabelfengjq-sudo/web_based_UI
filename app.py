import pandas as pd
from io import BytesIO
import random
import streamlit as st
import matplotlib.pyplot as plt

from utils import (
    excel_sheet_names,
    extract_codes_list,
    normalize_braced_value,
    numeric_like,
    read_excel_sheet,
    select_ids_from_df,
)


st.set_page_config(page_title="Row Locator", layout="wide")


def init_state() -> None:
    defaults = {
        "df": None,
        "resp_col": "Respondent_Serial",
        "upload_bytes": None,
        "upload_name": None,
        "sheet_name": None,
        "selected_columns": [],
        "matched_ids_list": [],
        "raw_table": None,
        "filtered_table": None,
        "filtered_quota_cols": [],
        "filtered_table_with_bins": None,
        "inspected_table": None,
        "inspected_table_with_bins": None,
        "selected_rows_from_inspected": None,
        "inspected_quota_cols": [],
        "step54_independent_samples": None,
        "comparison_results": None,
    }
    for key, val in defaults.items():
        st.session_state.setdefault(key, val)


def show_df(df: pd.DataFrame, n: int = 150):
    """Render a dataframe safely (cast object cols to string to avoid Arrow errors)."""
    if df is None:
        return
    safe = df.copy()
    obj_cols = [c for c in safe.columns if pd.api.types.is_object_dtype(safe[c])]
    for c in obj_cols:
        safe[c] = safe[c].astype(str)
    st.dataframe(safe.head(n))


@st.cache_data(show_spinner=False)
def _sheet_names_cache(file_bytes: bytes):
    return excel_sheet_names(file_bytes)


@st.cache_data(show_spinner=False)
def _read_sheet_cache(file_bytes: bytes, sheet_name: str):
    return read_excel_sheet(file_bytes, sheet_name)


def step0_upload():
    st.header("Step 0/1 — Upload Excel and set ID column")
    st.markdown(
        """
        **What to do**
        - Upload the Excel file.
        - Pick the sheet to load.
        - Confirm the respondent ID column (default: `Respondent_Serial`).
        """
    )

    uploaded = st.file_uploader("Upload .xlsx", type=["xlsx"], key="uploader")
    resp_col_input = st.text_input("Respondent ID column", st.session_state["resp_col"])
    if resp_col_input and resp_col_input != st.session_state["resp_col"]:
        st.session_state["resp_col"] = resp_col_input.strip()

    if not uploaded:
        st.info("Waiting for an Excel file…")
        return

    file_bytes = uploaded.getvalue()
    st.session_state["upload_bytes"] = file_bytes
    st.session_state["upload_name"] = uploaded.name

    sheet_names = _sheet_names_cache(file_bytes)
    if not sheet_names:
        st.error("No sheets found in the uploaded file.")
        return

    default_idx = 0
    if st.session_state["sheet_name"] in sheet_names:
        default_idx = sheet_names.index(st.session_state["sheet_name"])

    sheet = st.selectbox("Sheet to load", options=sheet_names, index=default_idx)
    st.session_state["sheet_name"] = sheet

    df = _read_sheet_cache(file_bytes, sheet)
    st.session_state["df"] = df

    st.success(f"Loaded '{uploaded.name}' | sheet '{sheet}' with shape {df.shape}")
    if st.session_state["resp_col"] not in df.columns:
        st.warning(
            f"Column '{st.session_state['resp_col']}' not found. "
            "Update the ID column name or rename the column in your file."
        )

    st.write("Preview (first 30 rows):")
    show_df(df, 150)
    st.caption("Columns: " + ", ".join(df.columns.astype(str)))


def step2_pick_columns():
    st.header("Step 2 — Pick columns to filter")
    st.markdown(
        """
        **What to do**
        - Choose which columns you want to use in Step 3 for filtering respondents.
        - Toggle "Show ALL columns" to include non-numeric columns if needed.
        - Click "Confirm selection" to lock them in and normalize brace values like `{_3}`.
        """
    )
    df = st.session_state["df"]
    resp_col = st.session_state["resp_col"]
    if df is None:
        st.info("Upload data first.")
        return

    show_all = st.checkbox("Show ALL columns", value=True)
    if show_all:
        base_cols = [c for c in df.columns if c != resp_col]
    else:
        base_cols = [c for c in df.columns if c != resp_col and numeric_like(df[c])]

    selected = st.multiselect(
        "Columns to use in Step 3",
        base_cols,
        default=st.session_state["selected_columns"],
    )

    if st.button("Confirm selection"):
        st.session_state["selected_columns"] = selected

        for col in selected:
            df[col] = df[col].map(normalize_braced_value)
        st.session_state["df"] = df
        st.session_state["matched_ids_list"] = []  # reset downstream
        st.success(f"Saved {len(selected)} columns and normalized brace values.")


def step3_rules():
    st.header("Step 3 — Define rules & run filter")
    st.markdown(
        """
        **What to do**
        - For each selected column, pick an operator:
          - `eq`: cell must equal that single code (no extras).
          - `in`: cell contains any of the selected codes.
          - `mc`: cell contains all selected codes (may include extras).
          - `nc`: cell contains none of the selected codes.
        - Click **Run filter** to produce matched respondent IDs.
        """
    )
    df = st.session_state["df"]
    resp_col = st.session_state["resp_col"]
    cols = st.session_state["selected_columns"]
    if df is None or not cols:
        st.info("Pick columns in Step 2.")
        return

    st.write("Define rules (AND across columns):")
    rules = []
    for col in cols:
        vals = sorted({x for v in df[col].dropna() for x in extract_codes_list(v)})
        op = st.selectbox(f"{col} operator", ["eq", "in", "mc", "nc"], key=f"op-{col}")
        if op == "eq":
            value = st.selectbox(f"{col} value", vals, key=f"eq-{col}")
            if value is not None:
                rules.append({"column": col, "op": "eq", "values": [value]})
        else:
            value = st.multiselect(f"{col} values", vals, key=f"in-{col}")
            if value:
                rules.append({"column": col, "op": op, "values": value})

    if st.button("Run filter"):
        ids = select_ids_from_df(df, rules, respondent_col=resp_col)
        st.session_state["matched_ids_list"] = ids
        st.write(f"{len(ids)} matched IDs")
        show_df(pd.DataFrame({resp_col: ids}), len(ids))


def step4_raw_table():
    st.header("Step 4 — Build raw_table")
    st.markdown(
        """
        **What to do**
        - Pick the columns you want to keep alongside the matched IDs.
        - Click **Build table** to create `raw_table` (rows = matched IDs; columns = ID + your picks).
        """
    )
    df = st.session_state["df"]
    resp_col = st.session_state["resp_col"]
    ids = st.session_state["matched_ids_list"]
    if df is None or not ids:
        st.info("Complete Steps 1–3 first.")
        return

    cols = st.multiselect(
        "Columns to include (besides ID)",
        [c for c in df.columns if c != resp_col],
    )
    if st.button("Build table"):
        left = pd.DataFrame({resp_col: ids})
        right = df[df[resp_col].isin(ids)][[resp_col] + cols]
        raw = left.merge(right, on=resp_col, how="left")
        st.session_state["raw_table"] = raw
        st.success(f"raw_table built with shape {raw.shape}")
        show_df(raw, 150)


def step5_filter():
    st.header("Step 5.1 — Filter raw_table")
    st.caption("Pick operators and code(s); all active filters are ANDed together. Empty selections skip that column.")
    rt = st.session_state["raw_table"]
    resp_col = st.session_state["resp_col"]
    if rt is None:
        st.info("Run Step 4 first to build raw_table.")
        return

    filter_cols = [c for c in rt.columns if c != resp_col]

    def _allowed_vals(col: str):
        vals = set()
        for v in rt[col].dropna():
            vals.update(extract_codes_list(v))
        return sorted(vals) if vals else list(range(-100, 101))

    with st.form("filter_raw_table"):
        st.write("Pick per-column operators and code(s). Empty selection = skip.")
        filters = []
        for col in filter_cols:
            op = st.selectbox(
                f"{col} operator",
                ["in", "eq", "mc", "nc", "skip"],  # default shows values
                index=0,
                key=f"f-op-{col}",
            )
            vals = _allowed_vals(col)
            if op == "eq":
                val = st.selectbox(f"{col} value", vals, key=f"f-eq-{col}")
                if val is not None:
                    filters.append({"column": col, "op": "eq", "values": [val]})
            else:
                sel = st.multiselect(f"{col} values", vals, key=f"f-in-{col}")
                if sel and op != "skip":
                    filters.append({"column": col, "op": op, "values": sel})
        submitted = st.form_submit_button("Apply filters")

    if submitted:
        base = rt.copy()
        for f in filters:
            col = f["column"]; op = f["op"]; vals = f["values"]
            vals_set = {int(x) for x in vals}

            def row_match(v):
                codes = set(extract_codes_list(v))
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
                return True

            base = base[base[col].map(row_match)]

        st.session_state["filtered_table"] = base
        # reset quota bins when filtered_table changes; keep only quotas still present
        existing_quota = st.session_state.get("filtered_quota_cols", [])
        kept_quota = [c for c in existing_quota if c in base.columns]
        st.session_state["filtered_quota_cols"] = kept_quota
        st.session_state["filtered_table_with_bins"] = None
        st.success(f"filtered_table built: {len(base)} rows × {base.shape[1]} columns")
        show_df(base, 150)
        st.download_button(
            "Download filtered_table (CSV)",
            data=st.session_state["filtered_table"].to_csv(index=False),
            file_name="filtered_table.csv",
            mime="text/csv",
        )

    # 5.1.1 Append extra columns (quota) -----------------------------------
    ft = st.session_state.get("filtered_table")
    df_full = st.session_state.get("df")
    if ft is not None and df_full is not None:
        st.markdown("#### 5.1.1 — Append extra columns to filtered_table (quota columns)")
        st.markdown(
            """
            **What to do**
            - Pick extra columns from the original data to append into `filtered_table`.
            - These appended columns are treated as potential **quota columns** for binning in 5.1.2.
            """
        )
        id_col = resp_col if resp_col in ft.columns else ft.columns[0]
        available_cols = [c for c in df_full.columns if c != id_col]
        if not available_cols:
            st.info("No columns available (besides the ID).")
        else:
            extra_cols = st.multiselect(
                "Columns to append (you can also re-select existing ones to treat them as quota columns)",
                options=available_cols,
                key="ft-extra-cols",
            )
            if st.button("Append to filtered_table"):
                if not extra_cols:
                    st.warning("Select at least one column to append.")
                else:
                    to_merge = [c for c in extra_cols if c not in ft.columns]
                    merged = ft.copy()
                    if to_merge:
                        add_cols = [id_col] + to_merge
                        merged = ft.merge(
                            df_full[add_cols].drop_duplicates(subset=id_col),
                            on=id_col,
                            how="left",
                            suffixes=("", "_from_df"),
                        )
                        st.session_state["filtered_table"] = merged
                    else:
                        st.session_state["filtered_table"] = merged
                    existing_quota = st.session_state.get("filtered_quota_cols", [])
                    for c in extra_cols:
                        if c not in existing_quota:
                            existing_quota.append(c)
                    st.session_state["filtered_quota_cols"] = existing_quota
                    st.session_state["filtered_table_with_bins"] = None
                    appended_count = len(to_merge)
                    reused_count = len(extra_cols) - appended_count
                    st.success(
                        f"Updated quotas | appended {appended_count} new column(s), "
                        f"marked {reused_count} existing column(s). "
                        f"New filtered_table shape: {merged.shape}"
                    )
                    show_df(merged, 150)

    # 5.1.2 Bin quota columns ----------------------------------------------
    ft = st.session_state.get("filtered_table")
    quota_cols = st.session_state.get("filtered_quota_cols", [])
    if ft is not None and quota_cols:
        # keep quota columns that exist in the current table and dedupe
        filtered_quota = [c for c in quota_cols if c in ft.columns]
        filtered_quota = list(dict.fromkeys(filtered_quota))
        if filtered_quota != quota_cols:
            st.session_state["filtered_quota_cols"] = filtered_quota
        quota_cols = filtered_quota
        if not quota_cols:
            st.info("No quota columns found in the current filtered_table.")
        else:

            st.markdown("#### 5.1.2 — Customize bins for quota columns (no change to filtered_table)")
            st.markdown(
                """
                **What to do**
                - Choose a quota column and define custom bins by selecting codes for each bin.
                - Bins are stored in `filtered_table_with_bins` (the original `filtered_table` stays intact).
                - You can apply bins to multiple quota columns one by one; click **Apply bins** after each column.
                """
            )
            id_col = resp_col if resp_col in ft.columns else ft.columns[0]
            base_ft = ft  # original values for allowed codes
            ft_work = st.session_state.get("filtered_table_with_bins")
            if ft_work is None:
                ft_work = base_ft.copy()
            col_to_bin = st.selectbox("Quota column to bin", quota_cols, key="ft-bin-col")
            # display current binned info
            if ft_work is not None:
                st.caption(
                    f"Quota columns: {', '.join(quota_cols)} | "
                    f"Theoretical combinations (from bins): "
                    f"{int(pd.Series([ft_work[c].nunique(dropna=True) for c in quota_cols]).prod())} | "
                    f"Observed combinations in data: "
                    f"{int(ft_work[quota_cols].drop_duplicates().shape[0])}"
                )
            if col_to_bin:
                vals = set()
                for v in base_ft[col_to_bin].dropna():  # use original values for choices
                    vals.update(extract_codes_list(v))
                vals = sorted(vals) if vals else []
                max_bins = max(1, len(vals) or 10)
                default_bins = min(2, max_bins)
                num_bins = st.number_input(
                    "Number of bins", min_value=1, max_value=max_bins, value=default_bins
                )

                bin_defs = []
                for i in range(int(num_bins)):
                    sel = st.multiselect(
                        f"Bin {i+1} values",
                        vals,
                        key=f"ft-bin-{col_to_bin}-{i}",
                    )
                    bin_defs.append(set(int(x) for x in sel))

                if st.button("Apply bins (filtered_table)"):
                    used = set()
                    ok = True
                    for b in bin_defs:
                        if used & b:
                            ok = False
                            break
                        used |= b
                    if not ok or not used:
                        st.warning("Bins must be non-overlapping and not empty.")
                    else:
                        code_to_bin = {}
                        for idx, b in enumerate(bin_defs, start=1):
                            for code in b:
                                code_to_bin[code] = idx

                        def map_bin(v):
                            codes = extract_codes_list(v)
                            for c in codes:
                                if c in code_to_bin:
                                    return code_to_bin[c]
                            return None

                        ft_bt = ft_work.copy()
                        # always map from original base_ft values to allow re-binning the same column
                        ft_bt[col_to_bin] = base_ft[col_to_bin].map(map_bin)
                        st.session_state["filtered_table_with_bins"] = ft_bt
                        st.success(f"Binning applied to '{col_to_bin}'.")
                        show_df(ft_bt, 150)

    # 5.1.3 Sample evenly across quota-bin combinations --------------------
    ft_bt = st.session_state.get("filtered_table_with_bins")
    if ft_bt is not None:
        st.markdown("#### 5.1.3 — Sample rows evenly across quota-bin combinations")
        st.markdown(
            """
            **What to do**
            - Using `filtered_table_with_bins`, pick how many rows you want per unique combination of quota-bin columns.
            - The app will select up to that many rows per combination (sampling without replacement).
            - Result is stored in `selected_rows_from_filtered_bins` and IDs in `selected_ids_from_filtered_bins`.
            """
        )
        id_col = resp_col if resp_col in ft_bt.columns else ft_bt.columns[0]
        # quota columns are those added in 5.1.1 (tracked) and present in binned table
        quota_cols = [c for c in st.session_state.get("filtered_quota_cols", []) if c in ft_bt.columns]
        if not quota_cols:
            st.info("No quota columns found to build combinations.")
        else:
            sample_per_combo = st.number_input(
                "Rows per combination", min_value=1, value=1, step=1, key="ft-sample-per-combo"
            )
            if st.button("Sample rows per combination"):
                combos = ft_bt[quota_cols].apply(lambda row: tuple(row.tolist()), axis=1)
                combo_to_rows = {}
                for idx in ft_bt.index:
                    cval = combos.loc[idx]
                    combo_to_rows.setdefault(cval, []).append(idx)

                selected_idx = []
                warnings = []
                for combo, idxs in combo_to_rows.items():
                    if len(idxs) < sample_per_combo:
                        warnings.append(f"Combo {combo} has only {len(idxs)} rows (requested {sample_per_combo}). Selecting all available.")
                        take = idxs
                    else:
                        take = st.session_state.get("rng", None)
                        import random
                        take = random.sample(idxs, sample_per_combo)
                    selected_idx.extend(take)

                result = ft_bt.loc[selected_idx].reset_index(drop=True)
                st.session_state["selected_rows_from_filtered_bins"] = result
                st.session_state["selected_ids_from_filtered_bins"] = result[id_col].tolist()

                st.success(f"Selected {len(result)} rows across {len(combo_to_rows)} combination(s).")
                if warnings:
                    st.warning("\n".join(warnings))
                show_df(result, len(result))
                st.download_button(
                    "Download selected_rows_from_filtered_bins (CSV)",
                    data=st.session_state["selected_rows_from_filtered_bins"].to_csv(index=False),
                    file_name="selected_rows_from_filtered_bins.csv",
                    mime="text/csv",
                )

    # Persistent previews ---------------------------------------------------
    st.markdown("##### Current tables (for reference)")
    ft_now = st.session_state.get("filtered_table")
    if ft_now is not None:
        st.write(f"`filtered_table`: {ft_now.shape}")
        show_df(ft_now, 150)

    ft_bins_now = st.session_state.get("filtered_table_with_bins")
    if ft_bins_now is not None:
        st.write(f"`filtered_table_with_bins`: {ft_bins_now.shape}")
        show_df(ft_bins_now, 150)

    sel_bins = st.session_state.get("selected_rows_from_filtered_bins")
    if sel_bins is not None:
        st.write(f"`selected_rows_from_filtered_bins`: {sel_bins.shape}")
        show_df(sel_bins, len(sel_bins))


def step5_mention():
    st.header("Step 5.2 — Mention rate on raw_table")
    st.caption("Counts how many columns match your chosen rule per respondent, divided by total columns.")
    rt = st.session_state["raw_table"]
    resp_col = st.session_state["resp_col"]
    if rt is None:
        st.info("Run Step 4 first to build raw_table.")
        return

    data_cols = [c for c in rt.columns if c != resp_col]
    if not data_cols:
        st.warning("raw_table has no data columns besides the ID.")
        return

    all_codes = set()
    for col in data_cols:
        for v in rt[col].dropna():
            all_codes.update(extract_codes_list(v))
    code_choices = sorted(all_codes) if all_codes else list(range(-100, 101))

    mode = st.selectbox(
        "Mode", ["eq (single code)", "in (any of)", "mc (all selected)"], index=0
    )
    if mode == "eq (single code)":
        eq_val = st.selectbox("Code", code_choices, key="mr-eq")
        code_set = {int(eq_val)} if eq_val is not None else set()
        op = "eq"
    else:
        sel = st.multiselect("Codes", code_choices, key="mr-in")
        code_set = {int(x) for x in sel}
        op = "in" if mode.startswith("in") else "mc"

    if st.button("Run mention rate"):
        if not code_set:
            st.warning("Pick at least one code.")
        else:
            ids = []
            avgs = []
            for _, row in rt.iterrows():
                rid = row[resp_col]
                hits = 0
                for col in data_cols:
                    codes = set(extract_codes_list(row[col]))
                    if not codes:
                        continue
                    if op == "eq":
                        match = next(iter(code_set)) in codes
                    elif op == "in":
                        match = bool(codes & code_set)
                    else:  # mc
                        match = code_set.issubset(codes)
                    if match:
                        hits += 1
                avg = hits / len(data_cols) if data_cols else float("nan")
                ids.append(rid); avgs.append(avg)

            avg_df = pd.DataFrame({resp_col: ids, "Average": avgs})
            st.session_state["avg_num_of_times"] = avg_df
            st.success(f"avg_num_of_times built: {len(avg_df)} rows × 2 columns")
            show_df(avg_df, 150)
            st.download_button(
                "Download avg_num_of_times (CSV)",
                data=st.session_state["avg_num_of_times"].to_csv(index=False),
                file_name="avg_num_of_times.csv",
                mime="text/csv",
            )

    # 5.2.1 Distribution & visualization -----------------------------------
    avg_df = st.session_state.get("avg_num_of_times")
    if avg_df is not None and not avg_df.empty:
        st.markdown("#### 5.2.1 — Distribution and visualization")
        q = avg_df["Average"].quantile([0.25, 0.5, 0.75])
        q1, q2, q3 = q[0.25], q[0.5], q[0.75]
        st.write(f"Quartile cut points: Q1={q1:.4f}, Q2={q2:.4f}, Q3={q3:.4f}")

        bin_labels = ["Bottom 25%", "25–50%", "50–75%", "Top 25%"]
        ranks = avg_df["Average"].rank(method="average", pct=True)
        avg_bins = avg_df.copy()
        avg_bins["Bin"] = pd.cut(
            ranks,
            bins=[0, 0.25, 0.5, 0.75, 1],
            labels=bin_labels,
            include_lowest=True,
        )
        st.session_state["avg_bins"] = avg_bins[["Average", resp_col, "Bin"]]

        st.write("Respondent bin assignment (first 30 rows):")
        st.dataframe(avg_bins[[resp_col, "Average", "Bin"]].head(150))

        counts = avg_bins["Bin"].value_counts().reindex(bin_labels).fillna(0).astype(int)
        st.write("Counts per bin:")
        st.write(counts)

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.hist(avg_df["Average"], bins=20)
        ax.axvline(q1, linestyle="--", color="orange", label="Q1")
        ax.axvline(q2, linestyle="--", color="green", label="Q2")
        ax.axvline(q3, linestyle="--", color="red", label="Q3")
        ax.set_xlabel("Average")
        ax.set_ylabel("Number of respondents")
        ax.legend()
        st.pyplot(fig)

        bottom_ids = avg_bins.loc[avg_bins["Bin"] == "Bottom 25%", resp_col].tolist()
        st.write(f"Total in Bottom 25%: {len(bottom_ids)}")
        if bottom_ids:
            st.code("\n".join(str(x) for x in bottom_ids), language="text")

        st.download_button(
            "Download avg_bins (CSV)",
            data=st.session_state["avg_bins"].to_csv(index=False),
            file_name="avg_bins.csv",
            mime="text/csv",
        )


def step5_matrix_solver():
    st.header("Step 5.3 — 0/1 matrix, quotas, solver")
    st.caption("Turn code(s) into a 0/1 matrix, optionally add quota columns, bin them, and solve for target sums.")
    rt = st.session_state["raw_table"]
    resp_col = st.session_state["resp_col"]
    if rt is None:
        st.info("Run Step 4 first to build raw_table.")
        return

    data_cols = [c for c in rt.columns if c != resp_col]
    codes_all = set()
    for col in data_cols:
        for v in rt[col].dropna():
            codes_all.update(extract_codes_list(v))
    code_opts = sorted(codes_all) if codes_all else list(range(-100, 101))

    target_codes = st.multiselect(
        "Code(s) that must all be present for a cell to be 1",
        code_opts,
        key="it-codes",
    )
    st.caption("Use either the include list or the exclude list—not both.")
    exclude_codes = st.multiselect(
        "Code(s) that must NOT be present for a cell to be 1 (optional)",
        code_opts,
        key="it-exclude-codes",
    )

    if st.button("Create inspected_table"):
        include_set = set(int(x) for x in target_codes)
        exclude_set = set(int(x) for x in exclude_codes)
        if include_set and exclude_set:
            st.warning("Pick either required codes OR excluded codes, not both.")
        elif not include_set and not exclude_set:
            st.warning("Pick at least one code in either list.")
        else:
            inspected = rt.copy()

            if include_set:
                def cell_fn(v):
                    codes = set(extract_codes_list(v))
                    return 1 if include_set.issubset(codes) else 0
                mode_msg = f"require {sorted(include_set)}"
            else:
                def cell_fn(v):
                    codes = set(extract_codes_list(v))
                    return 1 if not (codes & exclude_set) else 0
                mode_msg = f"exclude {sorted(exclude_set)}"

            for col in data_cols:
                inspected[col] = inspected[col].map(cell_fn)

            st.session_state["inspected_table"] = inspected
            st.session_state["inspected_table_with_bins"] = None
            st.success(f"inspected_table created ({mode_msg}) with shape {inspected.shape}")
            st.dataframe(inspected.head(150))
            st.download_button(
                "Download inspected_table (CSV)",
                data=st.session_state["inspected_table"].to_csv(index=False),
                file_name="inspected_table.csv",
                mime="text/csv",
            )

    it = st.session_state.get("inspected_table")
    df_full = st.session_state.get("df")
    # 5.3.1 Append extra columns as quota columns ---------------------------
    if it is not None and df_full is not None:
        st.markdown("#### 5.3.1 Append extra columns as quota columns")
        st.caption("Optional: add more columns from the original data to use as quota dimensions.")
        id_col = resp_col if resp_col in it.columns else it.columns[0]
        available = [c for c in df_full.columns if c not in it.columns and c != id_col]
        extra = st.multiselect(
            "Columns to append from original data (treated as quota columns)",
            available,
            key="it-extra",
        )
        if st.button("Append to inspected_table"):
            if not extra:
                st.warning("Select at least one column to append.")
            else:
                base = df_full[df_full[id_col].isin(it[id_col])][[id_col] + extra]
                merged = it.merge(base.drop_duplicates(subset=id_col), on=id_col, how="left")
                st.session_state["inspected_table"] = merged
                st.session_state["inspected_quota_cols"] = extra
                st.success(f"Added {len(extra)} column(s). New shape: {merged.shape}")
                show_df(merged, 150)

    # 5.3.2 Binning quota columns ------------------------------------------
    it = st.session_state.get("inspected_table")
    quota_cols = st.session_state.get("inspected_quota_cols", [])
    if it is not None and quota_cols:
        st.markdown("#### 5.3.2 Bin quota columns (inspected_table_with_bins)")
        st.caption("Optional: map quota column values into custom bins for the solver.")
        id_col = resp_col if resp_col in it.columns else it.columns[0]
        bt = it.copy()
        if bt is not None:
            st.caption(
                f"Quota columns: {', '.join(quota_cols)} | "
                f"Theoretical combinations (from bins): "
                f"{int(pd.Series([bt[c].nunique(dropna=True) for c in quota_cols]).prod())} | "
                f"Observed combinations in data: "
                f"{int(bt[quota_cols].drop_duplicates().shape[0])}"
            )
        col_to_bin = st.selectbox("Quota column to bin", quota_cols)
        if col_to_bin:
            vals = set()
            for v in it[col_to_bin].dropna():
                vals.update(extract_codes_list(v))
            vals = sorted(vals) if vals else []
            max_bins = max(1, len(vals) or 10)
            default_bins = min(2, max_bins)
            num_bins = st.number_input(
                "Number of bins", min_value=1, max_value=max_bins, value=default_bins
            )

            bin_defs = []
            for i in range(int(num_bins)):
                sel = st.multiselect(
                    f"Bin {i+1} values",
                    vals,
                    key=f"bin-{col_to_bin}-{i}",
                )
                bin_defs.append(set(int(x) for x in sel))

            if st.button("Apply bins"):
                # check overlaps
                used = set()
                ok = True
                for b in bin_defs:
                    if used & b:
                        ok = False
                        break
                    used |= b
                if not ok or not used:
                    st.warning("Bins must be non-overlapping and not empty.")
                else:
                    code_to_bin = {}
                    for idx, b in enumerate(bin_defs, start=1):
                        for code in b:
                            code_to_bin[code] = idx

                    def map_bin(v):
                        codes = extract_codes_list(v)
                        for c in codes:
                            if c in code_to_bin:
                                return code_to_bin[c]
                        return None

                    bt[col_to_bin] = bt[col_to_bin].map(map_bin)
                    st.session_state["inspected_table_with_bins"] = bt
                    st.success(f"Binning applied to '{col_to_bin}'.")
                    show_df(bt, 150)

    # 5.3.3 Solver ----------------------------------------------------------
    it_base = st.session_state.get("inspected_table")
    if it_base is not None:
        st.markdown("#### 5.3.3 Find rows matching targets (with optional even quotas)")
        st.caption("Choose k, target sums for 0/1 columns, and (if binned quotas exist) enforce equal rows per combination.")
        tbl_binned = st.session_state.get("inspected_table_with_bins")
        tbl = tbl_binned if tbl_binned is not None else it_base
        id_col = resp_col if resp_col in tbl.columns else tbl.columns[0]
        # quota columns: those the user appended in 5.3.1 (tracked)
        quota_cols = [c for c in st.session_state.get("inspected_quota_cols", []) if c in tbl.columns]
        # solver columns: original 0/1 matrix columns only (exclude ID and quotas)
        data_cols_solver = [c for c in it_base.columns if c != id_col and c not in quota_cols]
        if not data_cols_solver:
            st.info("No 0/1 data columns to target. Create inspected_table first.")
        else:
            k = st.number_input("Rows to select (k)", min_value=1, value=20, step=1)
            targets = {}
            for col in data_cols_solver:
                targets[col] = st.number_input(
                    f"Target sum for {col}", min_value=0, max_value=int(k), value=0, step=1
                )

            def _run_solver():
                import pulp

                base_tbl = it_base.copy()
                base_tbl[data_cols_solver] = base_tbl[data_cols_solver].fillna(0).astype(int)
                tbl_local = tbl.copy()
                for c in data_cols_solver:
                    tbl_local[c] = base_tbl[c]

                if quota_cols:
                    combos = tbl_local[quota_cols].apply(lambda row: tuple(row.tolist()), axis=1)
                    combo_labels = []
                    seen = {}
                    for c in combos:
                        if c not in seen:
                            seen[c] = len(seen)
                            combo_labels.append(c)
                    num_combos = len(combo_labels)
                    if num_combos and k % num_combos != 0:
                        st.error(f"k must be divisible by #quota combinations ({num_combos}).")
                        return None, None
                    per_combo = k // num_combos if num_combos else None
                else:
                    combos = None
                    combo_labels = []
                    per_combo = None

                A = base_tbl[data_cols_solver].to_numpy(dtype=int)
                n_rows, n_cols = A.shape
                prob = pulp.LpProblem("RowSelection", pulp.LpMinimize)
                x_vars = [pulp.LpVariable(f"x_{i}", cat="Binary") for i in range(n_rows)]
                prob += 0
                prob += pulp.lpSum(x_vars) == k
                for j in range(n_cols):
                    prob += pulp.lpSum(A[i, j] * x_vars[i] for i in range(n_rows)) == targets[data_cols_solver[j]]

                if combo_labels:
                    combo_to_rows = {c: [] for c in combo_labels}
                    for i, c in enumerate(combos):
                        combo_to_rows[c].append(i)
                    for c in combo_labels:
                        prob += pulp.lpSum(x_vars[i] for i in combo_to_rows[c]) == per_combo

                status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
                if pulp.LpStatus[status] != "Optimal":
                    st.warning(f"No exact solution. Status: {pulp.LpStatus[status]}")
                    return None, None
                selected_idx = [i for i in range(n_rows) if pulp.value(x_vars[i]) > 0.5]
                return selected_idx, tbl_local

            if st.button("Run solver"):
                res, tbl_local = _run_solver()
                if res is not None:
                    sel_tbl = tbl_local.iloc[res].reset_index(drop=True)
                    st.session_state["selected_rows_from_inspected"] = sel_tbl
                    st.session_state["selected_ids_from_inspected"] = sel_tbl[id_col].tolist()
                    st.success(f"Found solution with {len(sel_tbl)} rows.")
                    st.write("Selected respondent IDs:")
                    st.write(sel_tbl[id_col].tolist())
                    show_df(sel_tbl, 150)
                    st.download_button(
                        "Download selected rows (CSV)",
                        data=sel_tbl.to_csv(index=False),
                        file_name="selected_rows.csv",
                        mime="text/csv",
                    )


def step5_independent_sampling():
    st.header("Step 5.4 — Independent filter + random respondent IDs (with optional quota)")
    st.caption(
        "Input is `raw_table` from Step 4. Each target column runs independently (OR-style across columns)."
    )
    rt = st.session_state["raw_table"]
    df_full = st.session_state.get("df")
    resp_col = st.session_state["resp_col"]
    if rt is None:
        st.info("Run Step 4 first to build raw_table.")
        return

    id_col = resp_col if resp_col in rt.columns else rt.columns[0]
    data_cols = [c for c in rt.columns if c != id_col]
    if not data_cols:
        st.warning("raw_table has no data columns besides the ID.")
        return

    def _allowed_vals(df_in: pd.DataFrame, col: str):
        vals = set()
        for v in df_in[col].dropna():
            vals.update(extract_codes_list(v))
        return sorted(vals) if vals else list(range(-100, 101))

    def _build_quota_table(ids: list, quota_cols: list[str]) -> pd.DataFrame:
        base = pd.DataFrame({id_col: ids}).drop_duplicates(subset=id_col)
        for qcol in quota_cols:
            src = None
            if qcol in rt.columns:
                src = rt[[id_col, qcol]].drop_duplicates(subset=id_col)
            elif df_full is not None and id_col in df_full.columns and qcol in df_full.columns:
                src = df_full[[id_col, qcol]].drop_duplicates(subset=id_col)

            if src is None:
                base[qcol] = pd.NA
            else:
                base = base.merge(src, on=id_col, how="left")
        return base

    def _apply_bins(df_in: pd.DataFrame, quota_cols: list[str], bin_defs_map: dict) -> pd.DataFrame:
        out = df_in.copy()
        for qcol in quota_cols:
            defs = bin_defs_map.get(qcol, [])
            if not defs:
                continue
            code_to_bin = {}
            for idx, codes in enumerate(defs, start=1):
                for code in codes:
                    code_to_bin[int(code)] = idx

            def _map_one(v):
                codes = extract_codes_list(v)
                for c in codes:
                    if c in code_to_bin:
                        return code_to_bin[c]
                return None

            out[qcol] = out[qcol].map(_map_one)
        return out

    def _quota_aware_sample(df_ids_quota: pd.DataFrame, quota_cols: list[str], sample_n: int):
        if sample_n <= 0 or df_ids_quota.empty:
            return [], {}, {}
        combo_series = df_ids_quota[quota_cols].apply(lambda row: tuple(row.tolist()), axis=1)
        combo_to_ids = {}
        for idx, combo in combo_series.items():
            rid = df_ids_quota.at[idx, id_col]
            combo_to_ids.setdefault(combo, [])
            if rid not in combo_to_ids[combo]:
                combo_to_ids[combo].append(rid)

        combos = list(combo_to_ids.keys())
        total_available = sum(len(v) for v in combo_to_ids.values())
        target = min(sample_n, total_available)
        if target <= 0:
            return [], {}, {c: len(combo_to_ids[c]) for c in combos}

        base_take = target // len(combos)
        remainder = target % len(combos)
        combo_order = combos.copy()
        random.shuffle(combo_order)
        desired = {c: base_take for c in combos}
        for c in combo_order[:remainder]:
            desired[c] += 1

        pools = {}
        selected_by_combo = {c: [] for c in combos}
        for c in combos:
            pool = combo_to_ids[c].copy()
            random.shuffle(pool)
            take = min(desired[c], len(pool))
            selected_by_combo[c].extend(pool[:take])
            pools[c] = pool[take:]

        selected_count = sum(len(v) for v in selected_by_combo.values())
        remaining = target - selected_count
        while remaining > 0:
            eligible = [c for c in combos if pools[c]]
            if not eligible:
                break
            random.shuffle(eligible)
            for c in eligible:
                if remaining <= 0:
                    break
                selected_by_combo[c].append(pools[c].pop())
                remaining -= 1

        selected_ids = []
        for c in combos:
            selected_ids.extend(selected_by_combo[c])
        random.shuffle(selected_ids)
        selected_counts = {c: len(v) for c, v in selected_by_combo.items() if v}
        total_counts = {c: len(v) for c, v in combo_to_ids.items()}
        return selected_ids, selected_counts, total_counts

    def _combo_counts(df_ids_quota: pd.DataFrame, quota_cols: list[str]) -> dict:
        if df_ids_quota.empty:
            return {}
        combo_series = df_ids_quota[quota_cols].apply(lambda row: tuple(row.tolist()), axis=1)
        counts = {}
        for combo in combo_series:
            counts[combo] = counts.get(combo, 0) + 1
        return counts

    def _combo_text(combo_counts: dict, quota_cols: list[str]) -> str:
        if not combo_counts:
            return ""
        parts = []
        for combo, cnt in combo_counts.items():
            label = ", ".join(f"{q}={v}" for q, v in zip(quota_cols, combo))
            parts.append(f"[{label}]={cnt}")
        return " | ".join(parts)

    st.markdown("#### 5.4.1 — Set independent filter rules and requested counts")
    saved_jobs = st.session_state.get("step54_jobs", [])
    saved_by_col = {j.get("column"): j for j in saved_jobs}
    with st.form("step5_4_independent_rules_form"):
        st.write("Each column will be processed independently with its own filter and sample size.")
        jobs = []
        op_opts = ["eq", "in", "mc", "nc"]
        for col in data_cols:
            st.markdown(f"**{col}**")
            prev = saved_by_col.get(col, {})
            default_op = prev.get("op", "eq")
            default_op_idx = op_opts.index(default_op) if default_op in op_opts else 0
            op = st.selectbox(
                f"{col} operator",
                op_opts,
                index=default_op_idx,
                key=f"s54-op-{col}",
            )
            vals = _allowed_vals(rt, col)
            prev_vals = [int(x) for x in prev.get("values", [])]
            if op == "eq":
                default_eq = prev_vals[0] if prev_vals else vals[0]
                default_eq_idx = vals.index(default_eq) if default_eq in vals else 0
                val = st.selectbox(f"{col} value", vals, index=default_eq_idx, key=f"s54-eq-{col}")
                selected_vals = [int(val)]
            else:
                default_multi = [x for x in prev_vals if x in vals]
                selected_vals = st.multiselect(
                    f"{col} values",
                    vals,
                    default=default_multi,
                    key=f"s54-vals-{col}",
                )
                selected_vals = [int(x) for x in selected_vals]
            sample_n = st.number_input(
                f"{col} random respondent count",
                min_value=0,
                value=int(prev.get("sample_n", 0)),
                step=1,
                key=f"s54-n-{col}",
            )
            jobs.append(
                {
                    "column": col,
                    "op": op,
                    "values": selected_vals,
                    "sample_n": int(sample_n),
                }
            )
        save_rules = st.form_submit_button("Save 5.4.1 settings")
    if save_rules:
        st.session_state["step54_jobs"] = jobs
        st.success("Saved Step 5.4.1 settings.")

    st.markdown("#### 5.4.2 — Add quota columns (optional)")
    quota_current = st.session_state.get("step54_quota_cols", [])
    quota_options = set(c for c in rt.columns if c != id_col)
    if df_full is not None:
        quota_options |= set(c for c in df_full.columns if c != id_col)
    quota_options = sorted(quota_options)
    picked_quota = st.multiselect(
        "Quota columns for Step 5.4",
        quota_options,
        default=[c for c in quota_current if c in quota_options],
        key="s54-quota-pick",
    )
    if st.button("Apply quota columns (5.4.2)"):
        quota_cols = list(dict.fromkeys(picked_quota))
        st.session_state["step54_quota_cols"] = quota_cols
        current_defs = st.session_state.get("step54_bin_defs", {})
        st.session_state["step54_bin_defs"] = {k: v for k, v in current_defs.items() if k in quota_cols}
        st.success(f"Saved {len(quota_cols)} quota column(s) for Step 5.4.")

    st.markdown("#### 5.4.3 — Customize bins for quota columns (optional)")
    quota_cols = st.session_state.get("step54_quota_cols", [])
    bin_defs_map = st.session_state.get("step54_bin_defs", {})
    if not quota_cols:
        st.info("No quota columns selected for Step 5.4.")
    else:
        st.caption(f"Current quota columns: {', '.join(quota_cols)}")
        col_to_bin = st.selectbox("Quota column to bin (5.4.3)", quota_cols, key="s54-bin-col")
        quota_preview = _build_quota_table(rt[id_col].dropna().drop_duplicates().tolist(), [col_to_bin])
        vals = _allowed_vals(quota_preview, col_to_bin)
        existing_defs = bin_defs_map.get(col_to_bin, [])
        default_bins = len(existing_defs) if existing_defs else min(2, max(1, len(vals)))
        num_bins = st.number_input(
            "Number of bins",
            min_value=1,
            max_value=max(1, len(vals) if vals else 1),
            value=int(default_bins),
            step=1,
            key=f"s54-num-bins-{col_to_bin}",
        )
        bin_defs = []
        for i in range(int(num_bins)):
            default_bin_vals = existing_defs[i] if i < len(existing_defs) else []
            default_bin_vals = [x for x in default_bin_vals if x in vals]
            sel = st.multiselect(
                f"Bin {i+1} values",
                vals,
                default=default_bin_vals,
                key=f"s54-bin-{col_to_bin}-{i}",
            )
            bin_defs.append(set(int(x) for x in sel))

        apply_bins_clicked = st.button("Apply bins for selected quota column (5.4.3)")
        clear_bins_clicked = st.button("Clear bins for selected quota column (5.4.3)")
        if apply_bins_clicked:
            used = set()
            ok = True
            cleaned_defs = []
            for b in bin_defs:
                if not b or (used & b):
                    ok = False
                    break
                used |= b
                cleaned_defs.append(sorted(b))
            if not ok:
                st.warning("Bins must be non-empty and non-overlapping.")
            else:
                new_defs = dict(bin_defs_map)
                new_defs[col_to_bin] = cleaned_defs
                st.session_state["step54_bin_defs"] = new_defs
                st.success(f"Saved {len(cleaned_defs)} bin(s) for '{col_to_bin}'.")
        if clear_bins_clicked:
            if col_to_bin in bin_defs_map:
                new_defs = dict(bin_defs_map)
                new_defs.pop(col_to_bin, None)
                st.session_state["step54_bin_defs"] = new_defs
            st.success(f"Cleared bins for '{col_to_bin}'.")

        current_defs = st.session_state.get("step54_bin_defs", {})
        if current_defs:
            st.caption("Current Step 5.4 bin definitions:")
            for qcol, defs in current_defs.items():
                show_text = ", ".join(f"Bin{i+1}:{d}" for i, d in enumerate(defs))
                st.write(f"{qcol} -> {show_text}")

    st.markdown("#### 5.4.4 — Run independent random selection (quota-aware if configured)")
    if st.button("Run Step 5.4 selection"):
        jobs_to_run = st.session_state.get("step54_jobs", [])
        if not jobs_to_run:
            st.session_state["step54_independent_samples"] = None
            st.warning("Save 5.4.1 settings first.")
            return

        quota_cols = st.session_state.get("step54_quota_cols", [])
        bin_defs_map = st.session_state.get("step54_bin_defs", {})
        missing_quota = [
            q for q in quota_cols
            if q not in rt.columns and not (df_full is not None and q in df_full.columns and id_col in df_full.columns)
        ]
        active_quota_cols = [q for q in quota_cols if q not in missing_quota]

        out_rows = []
        notices = []
        if missing_quota:
            notices.append(
                "Missing quota columns ignored: " + ", ".join(missing_quota)
            )
        notices.append(
            "Step 5.4 non-dup goal: each next column tries to avoid IDs already selected by previous columns."
        )

        used_ids_global = set()

        for job in jobs_to_run:
            col = job["column"]
            op = job["op"]
            vals = [int(x) for x in job["values"]]
            sample_n = int(job["sample_n"])

            if sample_n <= 0:
                continue
            if op != "eq" and not vals:
                notices.append(f"{col}: skipped because no values were selected.")
                continue

            conditions = [{"column": col, "op": op, "values": vals}]
            filtered_ids = select_ids_from_df(rt, conditions, respondent_col=id_col)
            filtered_set = set(filtered_ids)
            fresh_ids = [rid for rid in filtered_ids if rid not in used_ids_global]
            reused_pool_ids = [rid for rid in filtered_ids if rid in used_ids_global]

            sampled_ids = []
            combo_selected_txt = ""
            combo_total_txt = ""
            quota_mode = "No quota"
            reused_from_previous = 0

            if not filtered_ids:
                sampled_ids = []
            elif sample_n >= len(filtered_ids):
                sampled_ids = list(filtered_ids)
                reused_from_previous = sum(1 for rid in sampled_ids if rid in used_ids_global)
                if sample_n > len(filtered_ids):
                    notices.append(
                        f"{col}: requested {sample_n}, but only {len(filtered_ids)} matched; returned all."
                    )
                if active_quota_cols:
                    quota_mode = "Quota configured (all matched returned)"
            elif active_quota_cols:
                sampled_fresh = []
                if fresh_ids:
                    qtbl_fresh = _build_quota_table(fresh_ids, active_quota_cols)
                    qtbl_fresh_binned = _apply_bins(qtbl_fresh, active_quota_cols, bin_defs_map)
                    sampled_fresh, _, _ = _quota_aware_sample(
                        qtbl_fresh_binned, active_quota_cols, sample_n
                    )
                remaining = sample_n - len(sampled_fresh)
                sampled_reused = []
                if remaining > 0 and reused_pool_ids:
                    qtbl_reused = _build_quota_table(reused_pool_ids, active_quota_cols)
                    qtbl_reused_binned = _apply_bins(qtbl_reused, active_quota_cols, bin_defs_map)
                    sampled_reused, _, _ = _quota_aware_sample(
                        qtbl_reused_binned, active_quota_cols, remaining
                    )
                sampled_ids = sampled_fresh + sampled_reused
                random.shuffle(sampled_ids)
                reused_from_previous = len(sampled_reused)
                quota_mode = "Quota-aware balanced across combinations"
                qtbl_all = _build_quota_table(filtered_ids, active_quota_cols)
                qtbl_all_binned = _apply_bins(qtbl_all, active_quota_cols, bin_defs_map)
                qtbl_selected = _build_quota_table(sampled_ids, active_quota_cols)
                qtbl_selected_binned = _apply_bins(qtbl_selected, active_quota_cols, bin_defs_map)
                combo_total_txt = _combo_text(_combo_counts(qtbl_all_binned, active_quota_cols), active_quota_cols)
                combo_selected_txt = _combo_text(_combo_counts(qtbl_selected_binned, active_quota_cols), active_quota_cols)
                if reused_from_previous > 0:
                    notices.append(
                        f"{col}: reused {reused_from_previous} previously selected ID(s) because unique IDs were insufficient."
                    )
            else:
                if len(fresh_ids) >= sample_n:
                    sampled_ids = random.sample(fresh_ids, sample_n)
                    reused_from_previous = 0
                else:
                    sampled_ids = fresh_ids.copy()
                    random.shuffle(sampled_ids)
                    need = sample_n - len(sampled_ids)
                    fallback = random.sample(reused_pool_ids, need) if need > 0 else []
                    sampled_ids.extend(fallback)
                    random.shuffle(sampled_ids)
                    reused_from_previous = len(fallback)
                    if reused_from_previous > 0:
                        notices.append(
                            f"{col}: reused {reused_from_previous} previously selected ID(s) because unique IDs were insufficient."
                        )

            sampled_ids = [rid for rid in sampled_ids if rid in filtered_set]
            used_ids_global.update(sampled_ids)

            out_rows.append(
                {
                    "Column": col,
                    "Operator": op,
                    "Values": ", ".join(str(x) for x in vals),
                    "Requested_n": sample_n,
                    "Matched_n": len(filtered_ids),
                    "Selected_n": len(sampled_ids),
                    "Reused_from_previous_cols": reused_from_previous,
                    "Quota_mode": quota_mode,
                    "Available_by_combo": combo_total_txt,
                    "Selected_by_combo": combo_selected_txt,
                    "Selected_respondent_ids": sampled_ids,
                }
            )

        if not out_rows:
            st.session_state["step54_independent_samples"] = None
            st.warning(
                "No output produced. Set random respondent count > 0 for at least one column."
            )
            return

        result = pd.DataFrame(out_rows)
        st.session_state["step54_independent_samples"] = result
        st.success(f"Generated outputs for {len(result)} column(s).")
        if notices:
            st.warning("\n".join(notices))

        st.markdown("#### Selected respondent IDs by column")
        for _, row in result.iterrows():
            ids = row["Selected_respondent_ids"]
            st.write(
                f"{row['Column']} | {row['Operator']} [{row['Values']}] | "
                f"{row['Quota_mode']} -> {row['Selected_n']} ID(s), reused={row['Reused_from_previous_cols']}"
            )
            if row["Selected_by_combo"]:
                st.caption(f"Selected by combo: {row['Selected_by_combo']}")
            if ids:
                st.code("\n".join(str(x) for x in ids), language="text")
            else:
                st.code("(no matched IDs)", language="text")

        downloadable = result.copy()
        downloadable["Selected_respondent_ids"] = downloadable["Selected_respondent_ids"].map(
            lambda xs: ",".join(str(x) for x in xs)
        )
        st.download_button(
            "Download step5_4_selected_ids (CSV)",
            data=downloadable.to_csv(index=False),
            file_name="step5_4_selected_ids.csv",
            mime="text/csv",
        )

    existing = st.session_state.get("step54_independent_samples")
    if existing is not None and not existing.empty:
        st.markdown("#### Latest Step 5.4 result")
        show_df(existing, len(existing))


def tools_comparison():
    st.header("Tools: Comparison — Overlap by quota combinations")
    st.caption(
        "Upload 2+ tables, pick quota column(s) per table, and find overlapping respondent IDs per combination."
    )

    uploaded = st.file_uploader(
        "Upload CSV or Excel files (2 or more)", type=["csv", "xlsx"], accept_multiple_files=True, key="cmp-uploader"
    )

    if not uploaded:
        st.info("Upload at least two files to compare.")
        return
    if len(uploaded) < 2:
        st.warning("Need at least two files for comparison.")
        return

    @st.cache_data(show_spinner=False)
    def _read_bytes(name: str, data: bytes):
        if name.lower().endswith(".csv"):
            return pd.read_csv(BytesIO(data))
        return pd.read_excel(BytesIO(data))

    tables = []
    for idx, file in enumerate(uploaded):
        df_local = _read_bytes(file.name, file.getvalue())
        st.subheader(f"File {idx+1}: {file.name}")
        st.write(f"Shape: {df_local.shape}")
        show_df(df_local, 150)

        id_col = st.selectbox(
            f"Respondent ID column — {file.name}",
            options=list(df_local.columns),
            index=list(df_local.columns).index(st.session_state["resp_col"]) if st.session_state["resp_col"] in df_local.columns else 0,
            key=f"cmp-id-{idx}",
        )
        quota_cols = st.multiselect(
            f"Quota column(s) for {file.name}",
            options=[c for c in df_local.columns if c != id_col],
            key=f"cmp-quota-{idx}",
        )
        tables.append({"name": file.name, "df": df_local, "id_col": id_col, "quota_cols": quota_cols})

    if st.button("Run comparison"):
        # validate quota columns
        if any(not t["quota_cols"] for t in tables):
            st.warning("Select at least one quota column for each table.")
            return
        # enforce common quota set
        common_quota = set(tables[0]["quota_cols"])
        for t in tables[1:]:
            common_quota &= set(t["quota_cols"])
        if not common_quota:
            st.error("Quota columns must overlap across all tables. Pick at least one column present in every table.")
            return
        quota_cols = sorted(common_quota)

        def combos_map(df, id_col, qcols):
            base = df.dropna(subset=[id_col])
            grp = base.groupby(qcols)[id_col].apply(lambda s: set(s.dropna())).to_dict()
            return grp

        all_combo_keys = set()
        per_table_maps = []
        for t in tables:
            cmap = combos_map(t["df"], t["id_col"], quota_cols)
            per_table_maps.append(cmap)
            all_combo_keys.update(cmap.keys())

        results = []
        for combo in sorted(all_combo_keys):
            combo_vals = list(combo) if isinstance(combo, tuple) else [combo]
            ids_per_table = []
            counts = {}
            for t, cmap in zip(tables, per_table_maps):
                ids = cmap.get(combo, set())
                ids_per_table.append(ids)
                counts[f"{t['name']} count"] = len(ids)
            overlap = set.intersection(*ids_per_table) if ids_per_table else set()
            row = {col: val for col, val in zip(quota_cols, combo_vals)}
            row.update(counts)
            row["overlap_count"] = len(overlap)
            row["overlap_ids"] = sorted(overlap)
            results.append(row)

        if not results:
            st.info("No combinations found across the uploaded tables.")
            return

        res_df = pd.DataFrame(results)
        st.session_state["comparison_results"] = res_df
        st.success(f"Built comparison across {len(tables)} table(s) and {len(results)} combination(s).")
        show_df(res_df, len(res_df))
        st.download_button(
            "Download comparison (CSV)",
            data=res_df.to_csv(index=False),
            file_name="comparison_results.csv",
            mime="text/csv",
        )


def main():
    init_state()
    tabs = st.tabs([
        "Step 1: Upload",
        "Step 2: Pick columns",
        "Step 3: Rules",
        "Step 4: Raw table",
        "Step 5.1: Filter",
        "Step 5.2: Mention rate",
        "Step 5.3: Matrix & solver",
        "Step 5.4: Independent sampling",
        "Tools: Comparison",
    ])
    with tabs[0]:
        step0_upload()
    with tabs[1]:
        step2_pick_columns()
    with tabs[2]:
        step3_rules()
    with tabs[3]:
        step4_raw_table()
    with tabs[4]:
        step5_filter()
    with tabs[5]:
        step5_mention()
    with tabs[6]:
        step5_matrix_solver()
    with tabs[7]:
        step5_independent_sampling()
    with tabs[8]:
        tools_comparison()


if __name__ == "__main__":
    main()
