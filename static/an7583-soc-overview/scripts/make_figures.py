#!/usr/bin/env python3
"""Regenerate the bar charts of the AN7583 survey article.

Every number below also appears in a table in the article. Run from any
directory: images are written to ../img relative to this script.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "img"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
ORANGE = "#eb6834"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def _axes(fig_h, title, xlabel):
    fig, ax = plt.subplots(figsize=(8.0, fig_h), dpi=150)
    ax.set_title(title, loc="left", color=INK, fontsize=12, pad=12)
    ax.set_xlabel(xlabel)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _bar(ax, y, x0, x1, h, color):
    ax.barh(y, x1 - x0, left=x0, height=h, color=color, linewidth=0)


def single(name, title, xlabel, rows, fmt="{:g}", xmax=None, note=None):
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    fig, ax = _axes(0.55 * len(rows) + 1.3, title, xlabel)
    top = xmax or max(vals) * 1.18
    ax.set_xlim(0, top)
    ys = list(range(len(rows)))[::-1]
    for y, v in zip(ys, vals):
        _bar(ax, y, 0, v, 0.5, BLUE)
        ax.text(v + top * 0.01, y, fmt.format(v), va="center", color=INK, fontsize=9)
    ax.set_yticks(ys, labels)
    if note:
        fig.text(0.01, 0.01, note, color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.04 if note else 0, 1, 1))
    fig.savefig(OUT / name)
    plt.close(fig)


def grouped(name, title, xlabel, groups, series, fmt="{:g}", note=None):
    """groups: [(label, [v_series0, v_series1])]; series: [(name, color)]."""
    n = len(series)
    fig, ax = _axes(0.9 * len(groups) + 2.0, title, xlabel)
    top = max(max(v) for _, v in groups) * 1.2
    ax.set_xlim(0, top)
    h = 0.32
    ys = [i * (n * h + 0.45) for i in range(len(groups))][::-1]
    for y, (_, vals) in zip(ys, groups):
        for k, (v, (_, color)) in enumerate(zip(vals, series)):
            yy = y + (n - 1) * h / 2 - k * h
            _bar(ax, yy, 0, v, h - 0.04, color)
            ax.text(v + top * 0.01, yy, fmt.format(v), va="center", color=INK, fontsize=9)
    ax.set_yticks(ys, [g[0] for g in groups])
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in series]
    ax.legend(handles, [s for s, _ in series], loc="upper left", frameon=False,
              labelcolor=INK2, ncol=len(series), bbox_to_anchor=(0, -0.16))
    if note:
        fig.text(0.01, 0.01, note, color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.04 if note else 0, 1, 1))
    fig.savefig(OUT / name)
    plt.close(fig)


def ranges(name, title, xlabel, rows, note=None):
    """rows: [(label, low, high)] drawn as floating bars."""
    fig, ax = _axes(0.6 * len(rows) + 1.3, title, xlabel)
    top = max(r[2] for r in rows) * 1.2
    ax.set_xlim(0, top)
    ys = list(range(len(rows)))[::-1]
    for y, (_, lo, hi) in zip(ys, rows):
        ax.barh(y, hi - lo, left=lo, height=0.5, color=BLUE, linewidth=0)
        ax.text(hi + top * 0.01, y, f"{lo:g}-{hi:g}", va="center", color=INK, fontsize=9)
    ax.set_yticks(ys, [r[0] for r in rows])
    if note:
        fig.text(0.01, 0.01, note, color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, 0.04 if note else 0, 1, 1))
    fig.savefig(OUT / name)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)

    # Fig. 2: DRAM reserved at boot (MiB), from the reserved-memory layout
    single("fig02-reserved-dram.png",
           "DRAM carved out at boot, per consumer",
           "MiB",
           [("Secure monitor (0x80000000)", 2),
            ("NPU code (0x84000000)", 10),
            ("QDMA0 forward buffers (0x87000000)", 32),
            ("QDMA1 forward buffers (0x89000000)", 16),
            ("NPU rx packet pool (0x8A000000)", 24),
            ("NPU tx packet pool (0x8B800000)", 26),
            ("NPU tx buffer ids (0x8D200000)", 0.025)],
           fmt="{:g}")

    # Fig. 12: NPU load latency per memory level (cycles)
    single("fig12-npu-memory-cost.png",
           "NPU hart load latency by memory level",
           "cycles per load",
           [("Own DRAM data, D-cache hit", 10),
            ("Cluster SRAM", 17),
            ("NPU SRAM", 18),
            ("Host DRAM, uncached", 98)])

    # Fig. 13: NPU cycles per 1500-byte frame
    single("fig13-npu-frame-cost.png",
           "NPU cycles per 1500-byte frame, by path",
           "cycles",
           [("Wi-Fi to host, payload copied by copy engine", 5800),
            ("Host to Wi-Fi, payload copied (worst case)", 7800),
            ("LAN to Wi-Fi, descriptor only (tx hart)", 2350)],
           fmt="{:,.0f}",
           note="Copy-engine paths share about 2Gbps of copy bandwidth across all host traffic.")

    # Fig. 15a: host CPU load, CPU path vs hardware path
    grouped("fig15a-cpu-load.png",
            "Host CPU load: software path vs hardware path",
            "host CPU busy, % of both cores",
            [("WAN to Wi-Fi (routed)", [80, 5]),
             ("Wi-Fi to WAN (routed)", [50, 3.5]),
             ("Wi-Fi to LAN, 5GHz (bridged)", [62, 2.2])],
            [("software path", ORANGE), ("hardware path (PPE + NPU)", BLUE)])

    # Fig. 15b: 5GHz throughput, CPU path vs hardware path
    grouped("fig15b-throughput-5g.png",
            "5GHz LAN to Wi-Fi throughput: software path vs hardware path",
            "Mbps",
            [("TCP, 4 streams", [761, 857]),
             ("UDP 1472 B, 4 streams", [651, 925]),
             ("UDP 64 B, 4 streams", [35.3, 133])],
            [("software path", ORANGE), ("hardware path (PPE + NPU)", BLUE)],
            note="LAN client on a 1Gbps port: the 857-925Mbps results sit at that port's limit.")

    # Fig. 16: Wi-Fi throughput per band, one or more clients, hardware path
    single("fig16-wifi-throughput.png",
           "Wi-Fi throughput through the hardware path",
           "Mbps",
           [("2.4GHz, 2x2 client, download", 400),
            ("2.4GHz, 2x2 client, upload", 419),
            ("5GHz, Wi-Fi 7 client, 1 stream", 1470),
            ("5GHz, Wi-Fi 7 client, upload", 1407),
            ("5GHz, Wi-Fi 6 client, download", 1776),
            ("Both bands at once", 2071)],
           fmt="{:,.0f}")

    # Fig. 19: TCP terminated on the host CPU
    single("fig19-host-tcp.png",
           "TCP terminated on the host CPU (2x Cortex-A53)",
           "Mbps",
           [("LAN host to SoC (1GbE)", 941),
            ("WAN host to SoC", 1820),
            ("SoC to WAN host", 2130),
            ("SoC to Wi-Fi 7 client", 1048)],
           fmt="{:,.0f}",
           note="Receiving 1.8Gbps uses 1.6-1.7 of the 2 cores.")

    # Fig. 17: in-chip queueing delay with and without AQM in the NPU tx path
    ranges("fig17-aqm-delay.png",
           "In-chip queue delay, 16 TCP streams on 2.4GHz",
           "ms (range over runs)",
           [("NPU queue management on", 16, 19),
            ("NPU queue management off", 41, 152)])


if __name__ == "__main__":
    main()
