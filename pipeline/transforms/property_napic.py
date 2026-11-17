"""Parse NAPIC Excel releases for the property transform.

Port of the NAPIC half of scripts/property/property.R (tableau_data_prep repo),
which the first Python migration left out. Each *_table() function takes one
sheet read with header=None and returns tidy Penang rows. Tables are located by
their header text, not R's fixed cell ranges, because the 2021+ releases moved
the tables down two rows. Anything that does not match the expected layout
raises LayoutError: a loud failure beats silently writing partial data.

Deliberate differences from R (all bugs in the R output):
  - File quarters are read from every naming style. R's pattern missed
    "Q3 2023"-style names, so it kept two copies of Q3 2023 transactions.
  - "Detach"/"Detached" and "Terrace"/"Terraced" headers map to one label each.
    R produced "Detacheded" and "terraced" once NAPIC renamed its headers.
"""

from __future__ import annotations

import re

import pandas as pd


class LayoutError(ValueError):
    """A NAPIC file or sheet does not match the layout this parser expects."""


SECTORS = ("Residential", "Commercial", "Industrial", "Agriculture", "Development", "Others", "Total")
MEASURES = ("Minimum", "25th Percentile", "Mean", "Median", "75th Percentile", "Maximum")
UNSOLD_TABLES = {"TABLE 2": "Overhang", "TABLE 4": "Under construction", "TABLE 6": "Not constructed"}
UNSOLD_VALUE_COLS = {
    "unit": "Number of units launched",
    "unsold": "Number of unsold units",
    "value": "Unsold value (RM mil)",
}
# Newly launched "Units" columns, left to right: (header letters, output label).
LAUNCH_TYPES = (
    ("singlestoreyterrace", "Single storey terrace"),
    ("storeyterrace", "2/3 storey terrace"),
    ("singlestoreysemidetached", "Single storey semi-detached"),
    ("storeysemidetached", "2/3 storey semi-detached"),
    ("detached", "Detached"),
    ("townhouse", "Townhouse"),
    ("cluster", "Cluster"),
    ("lowcosthouse", "Low-cost house"),
    ("lowcostflat", "Low-cost flat"),
    ("flat", "Flat"),
    ("condominiumapartment", "Condominium/apartment"),
)

_FILE_QUARTER = re.compile(r"(?<!\d)(\d{4})\s*Q([1-4])|Q([1-4])\s*(\d{4})(?!\d)", re.I)
_TABLE_QUARTER = re.compile(r"Q([1-4])\s*(\d{4})", re.I)
_YEAR = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


# --- small helpers -----------------------------------------------------------

def _text(value) -> str:
    """Cell as text with whitespace squished; blank for empty cells."""
    return "" if pd.isna(value) else " ".join(str(value).split())


def _sentence(text: str) -> str:
    """R's str_to_sentence: first letter upper, the rest lower."""
    return text[:1].upper() + text[1:].lower()


def _tight(text: str) -> str:
    """Drop spaces around '-' and '/' ("2 -3" -> "2-3", "a/ b" -> "a/b")."""
    return re.sub(r"\s*([-/])\s*", r"\1", text)


def _price(text: str) -> str:
    return _tight(" ".join(text.replace("RM", "").split()))


def quarter_start(year: int, quarter: int) -> pd.Timestamp:
    return pd.Timestamp(year=year, month=3 * (quarter - 1) + 1, day=1)


def file_quarter(name: str) -> pd.Timestamp:
    """Release quarter from a file name in any NAPIC style.

    Handles "2017 Q1", "2019Q4", "Q1 2023", "PINANGQ12022" and
    "...Q32021(Revise08122021)".
    """
    m = _FILE_QUARTER.search(name)
    if not m:
        raise LayoutError(f"No release quarter in file name {name!r}")
    year, quarter = (m[1], m[2]) if m[1] else (m[4], m[3])
    return quarter_start(int(year), int(quarter))


def file_year(name: str) -> int:
    years = _YEAR.findall(name)
    if not years:
        raise LayoutError(f"No year in file name {name!r}")
    return int(years[-1])


def _table_quarter(label: str) -> pd.Timestamp:
    m = _TABLE_QUARTER.search(label)
    if not m:
        raise LayoutError(f"Unreadable quarter label {label!r}")
    return quarter_start(int(m[2]), int(m[1]))


def normalise_type(raw: str) -> str:
    """Property type label as R wrote it, minus R's Detacheded/terraced drift."""
    label = _tight(_sentence(_text(raw)))
    label = re.sub(r"\b([dD])etach(?:ed)*\b", r"\1etached", label)  # also repairs "Detacheded"
    label = re.sub(r"\bterraced\b", "terrace", label)
    return label.replace("Low cost", "Low-cost")


def _find(df: pd.DataFrame, pattern: str) -> tuple[int, int]:
    """(row, col) position of the first cell whose text fully matches pattern."""
    rx = re.compile(pattern, re.I)
    for r in range(len(df)):
        for c in range(df.shape[1]):
            if rx.fullmatch(_text(df.iat[r, c])):
                return r, c
    raise LayoutError(f"No cell matching {pattern!r}")


def pick_sheet(sheet_names: list[str], pattern: str) -> str:
    hits = [s for s in sheet_names if re.fullmatch(pattern, s.strip(), re.I)]
    if len(hits) != 1:
        raise LayoutError(f"Expected one sheet matching {pattern!r}, found {hits}")
    return hits[0]


def _positions(groups: pd.Series, labels: list, what: str) -> pd.Series:
    """Map each row to labels[i], i = its position within its group.

    NAPIC tables print the quarter/status label only on the first group and
    repeat the same row order in every group; R recycled the labels the same way.
    """
    sizes = groups.groupby(groups, sort=False).size()
    if not labels or (sizes != len(labels)).any():
        raise LayoutError(f"{what}: groups of {sorted(set(sizes))} rows, expected {len(labels)}")
    return groups.groupby(groups, sort=False).cumcount().map(dict(enumerate(labels)))


# --- sales: tables 6.1 (count) and 6.3 (value, RM million) -------------------

def sales_table(df: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """Price range x quarter x sector rows from table 6.1 or 6.3."""
    hr, pc = _find(df, r"price range")
    header = [_text(v).lower() for v in df.iloc[hr]]
    cols = {}
    for sector in SECTORS:
        hits = [i for i, h in enumerate(header) if h.startswith(sector.lower()[:6])]
        if len(hits) != 1:
            raise LayoutError(f"Sector column {sector!r} found {len(hits)} times")
        cols[sector] = hits[0]

    body = df.iloc[hr + 1:]
    stop = body[pc].map(_text).str.lower().eq("total").to_numpy()
    if not stop.any():
        raise LayoutError("No 'Total' row closing the price ranges")
    body = body.iloc[: stop.argmax()]

    values = body[list(cols.values())].apply(pd.to_numeric, errors="coerce")
    keep = values.notna().any(axis=1)
    body, values = body[keep], values[keep].set_axis(list(cols), axis=1)
    prices = body[pc].map(lambda v: "" if pd.isna(v) else str(v).strip()).replace("", pd.NA).ffill()
    quarters = [_table_quarter(q) for q in dict.fromkeys(body[pc + 1].map(_text)) if q]

    out = values.assign(**{"Price range": prices, "Date": _positions(prices, quarters, "sales")})
    return out.melt(id_vars=["Price range", "Date"], var_name="Sub-sector", value_name=value_name)


def parse_sales(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Join count (6.1) and value (6.3) like R: Value (RM) = RM million x 1e6."""
    names = list(sheets)
    count = sales_table(sheets[pick_sheet(names, r"6\.1(?!\d).*")], "Number")
    value = sales_table(sheets[pick_sheet(names, r"6\.3(?!\d).*")], "Value (RM)")
    value["Value (RM)"] = (value["Value (RM)"] * 1_000_000).round()
    return value.merge(count, on=["Price range", "Date", "Sub-sector"], how="left", validate="one_to_one")


# --- residential house prices: "Keseluruhan" summary sheet -------------------

def house_price_table(df: pd.DataFrame, year: int) -> pd.DataFrame:
    hr, sc = _find(df, r"country\s*/\s*state")
    body = df.iloc[hr + 1:, sc:sc + 1 + len(MEASURES)]
    states = body.iloc[:, 0].map(_text)
    values = body.iloc[:, 1:].apply(pd.to_numeric, errors="coerce").set_axis(list(MEASURES), axis=1)
    keep = states.ne("") & values.notna().any(axis=1)
    states = (
        states[keep].str.title().str.replace(r"^Wp\b", "", regex=True).str.strip()
        .replace("Pulau Pinang", "Penang")
    )
    out = values[keep].assign(State=states).melt(id_vars="State", var_name="Measure", value_name="House price")
    out = out.dropna(subset=["House price"])
    return out.assign(Year=year)[["Year", "State", "Measure", "House price"]]


# --- unsold: TABLE 2 overhang, TABLE 4 under construction, TABLE 6 not built --

def unsold_table(df: pd.DataFrame, status: str) -> pd.DataFrame:
    hr, sc = _find(df, r"state")
    header = [_text(v) for v in df.iloc[hr]]
    pc = sc + 1
    if header[pc].lower() != "price range":
        raise LayoutError(f"Expected 'Price Range' after 'State', got {header[pc]!r}")
    num_cols = [c for c in range(pc + 1, len(header)) if header[c]]
    type_cols = [c for c in num_cols if header[c].lower() != "total"]

    col0 = df.iloc[hr + 1:, sc].map(_text)
    labels = list(dict.fromkeys(v for v in col0 if v and v != v.upper()))
    out_cols = []
    for label in labels:
        key = next((k for k in UNSOLD_VALUE_COLS if label.lower().startswith(k)), None)
        if key is None:
            raise LayoutError(f"Unknown row label {label!r}")
        out_cols.append(UNSOLD_VALUE_COLS[key])

    starts = col0.index[col0.eq("PULAU PINANG")]
    if len(starts) != 1:
        raise LayoutError("Expected exactly one PULAU PINANG block")
    rest = col0.loc[starts[0] + 1:]
    nxt = rest.index[rest.ne("") & rest.eq(rest.str.upper())]
    block = df.loc[starts[0] + 1: (nxt[0] - 1 if len(nxt) else df.index[-1])]

    numbers = block[num_cols].apply(pd.to_numeric, errors="coerce")
    block = block[numbers.notna().any(axis=1)]
    prices = block[pc].map(_text).replace("", pd.NA).ffill()
    statuses = _positions(prices, out_cols, f"unsold {status}")

    long = (
        block[type_cols].apply(pd.to_numeric, errors="coerce")
        .set_axis([normalise_type(header[c]) for c in type_cols], axis=1)
        .assign(**{"Price range": prices.map(_price), "_status": statuses})
        .melt(id_vars=["Price range", "_status"], var_name="Type")
    )
    wide = long.pivot(index=["Price range", "Type"], columns="_status", values="value").reset_index()
    wide = wide.reindex(columns=["Price range", "Type", *UNSOLD_VALUE_COLS.values()])
    wide = wide[wide["Price range"].str.upper().ne("TOTAL")]
    return wide.assign(**{"Status of property": status})


def parse_unsold(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    names = list(sheets)
    return pd.concat(
        [unsold_table(sheets[pick_sheet(names, t)], s) for t, s in UNSOLD_TABLES.items()],
        ignore_index=True,
    )


# --- newly launched residential units: "PULAU PINANG" sheet ------------------

def newly_launched_table(df: pd.DataFrame) -> pd.DataFrame:
    """Rows per launch quarter x district x type x price range (wide measures)."""
    hr, c0 = _find(df, r"state\s*&\s*district")
    header = [re.sub(r"[^a-z]", "", _text(v).lower()) for v in df.iloc[hr]]
    unit_cols = [c for c in range(c0 + 4, len(header)) if header[c]]
    found = [header[c] for c in unit_cols]
    expected = [k for k, _ in LAUNCH_TYPES] + ["total"]
    if found != expected:
        raise LayoutError(f"Property type headers changed: {found}")
    unit_cols = unit_cols[:-1]  # drop Total, as R did

    rows = []
    launched = region = price = None
    for r in range(hr + 1, len(df)):
        first = _text(df.iat[r, c0])
        if first:
            m = re.match(r"LAUNCHED (?:WITH)*IN (.+)", first, re.I)
            if m:
                launched = _table_quarter(m[1]) if _TABLE_QUARTER.search(m[1]) else None
            else:
                region = first.title()
        price = _text(df.iat[r, c0 + 1]) or price
        time, measure = _text(df.iat[r, c0 + 2]), _text(df.iat[r, c0 + 3])
        within = re.fullmatch(r"Within (\d+) Months", time, re.I)
        if measure.lower() == "unit launched":
            column = "Newly launches"
        elif within:
            column = f"Sold units (W{within[1]})"
        else:
            continue
        if launched is None or not price or price.upper() == "TOTAL" or region in (None, "Pulau Pinang"):
            continue
        values = pd.to_numeric(df.iloc[r, unit_cols], errors="coerce")
        if values.isna().all():
            continue
        for (_, label), value in zip(LAUNCH_TYPES, values):
            rows.append((launched, region, label, _sentence(_price(price)), column, value))

    long = pd.DataFrame(rows, columns=["Date", "District", "Property type", "Price range", "_col", "value"])
    keys = ["Date", "District", "Property type", "Price range"]
    wide = long.pivot(index=keys, columns="_col", values="value").reset_index()
    wide.columns.name = None
    return wide
