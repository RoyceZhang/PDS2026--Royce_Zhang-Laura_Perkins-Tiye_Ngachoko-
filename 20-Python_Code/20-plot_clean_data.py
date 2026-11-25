from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter

data_dir = Path("10-Clean_Data")
pep = pd.read_parquet(data_dir / "pep_county_race_2006_2015.parquet")
snap = pd.read_parquet(data_dir / "saipe_snap_2006_2015.parquet")

plot_dir = Path("30-Exported_Files") / "10-Plots"
plot_dir.mkdir(parents=True, exist_ok=True)

states = ["FL", "NC", "SC", "AZ", "WA"]
colors = {
    "FL": "#2a78d6",
    "NC": "#eb6834",
    "SC": "#1baf7a",
    "AZ": "#eda100",
    "WA": "#e87ba4",
}
millions = FuncFormatter(lambda x, _: f"{x / 1e6:.1f}M")
percent = PercentFormatter(decimals=0)


def plot_by_state(totals, value_col, title, ylabel, filename, y_format):
    """totals: one row per state-year with a value_col column"""
    fig, ax = plt.subplots(figsize=(10, 6))
    for st in states:
        d = totals[totals["state_abbreviation"] == st]
        ax.plot(
            d["year"],
            d[value_col],
            color=colors[st],
            linewidth=2,
            marker="o",
            markersize=4,
            label=st,
        )
        ax.annotate(
            st,
            (d["year"].iloc[-1], d[value_col].iloc[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            color="#333",
        )

    ax.axvline(2010, color="#999", linestyle="--", linewidth=1)
    ax.axvline(2012, color="#999", linestyle=":", linewidth=1)
    ax.set_title(title)
    ax.set_xlabel("Year")
    ax.set_ylabel(ylabel)
    ax.set_xticks(range(2006, 2016))
    ax.yaxis.set_major_formatter(y_format)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e5e5e5")
    ax.legend(frameon=False, loc="upper left")

    fig.tight_layout()
    out_file = plot_dir / filename
    fig.savefig(out_file, dpi=200)
    print("saved", out_file.resolve())
    plt.close(fig)


# state totals for each dataset
pop_totals = pep.groupby(["state_abbreviation", "year"], as_index=False)[
    "total_pop"
].sum()
snap_totals = snap.groupby(["state_abbreviation", "year"], as_index=False)[
    "snap_recipients"
].sum()

# SNAP recipients as a share of population
rate = snap.merge(
    pep[["county_fips", "year", "total_pop"]], on=["county_fips", "year"], how="inner"
)
assert len(rate) == len(snap), "some SNAP rows had no matching population row"
rate = rate.groupby(["state_abbreviation", "year"], as_index=False)[
    ["snap_recipients", "total_pop"]
].sum()
rate["snap_pct"] = rate["snap_recipients"] / rate["total_pop"] * 100
assert rate["snap_pct"].between(3, 30).all(), rate[~rate["snap_pct"].between(3, 30)]

plot_by_state(
    pop_totals,
    "total_pop",
    "Total population by state, 2006–2015",
    "Population",
    "pep_population_by_state.png",
    millions,
)

plot_by_state(
    snap_totals,
    "snap_recipients",
    "SNAP recipients by state, 2006–2015",
    "SNAP recipients (July)",
    "snap_recipients_by_state.png",
    millions,
)

plot_by_state(
    rate,
    "snap_pct",
    "Share of population receiving SNAP, 2006–2015",
    "SNAP recipients (% of population)",
    "snap_share_by_state.png",
    percent,
)
