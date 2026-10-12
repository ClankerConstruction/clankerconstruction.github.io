#!/usr/bin/env python3
"""Regenerate the charts of the accelerated-datapaths article.

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
AQUA = "#1baf7a"
YELLOW = "#eda100"

# X19, filled from tools/article-accel/data/s5-*.jsonl (medians)
WIFI_CPU = [("plain forwarding", [1.16, 1.10, 1.52]), ("software flowtable", [0.93, 0.98, 1.51]),
            ("PPE, radio receive via the host", [0.25, 0.78, 0.06]), ("PPE", [0.04, 0.06, 0.05])]
WIFI_NOTE = ("5GHz 160MHz 2-stream client; TCP 4 connections (about 360-400 Mbps down, 590-610 up on every path); "
             "64-byte: about 145 kpps offered")

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


def _axes(fig_h, title, xlabel, w=8.0):
    fig, ax = plt.subplots(figsize=(w, fig_h), dpi=150)
    ax.set_title(title, loc="left", color=INK, fontsize=12, pad=12)
    ax.set_xlabel(xlabel)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _save(fig, name, note=None, bottom=None):
    if note:
        fig.text(0.01, 0.01, note, color=INK2, fontsize=8)
    fig.tight_layout(rect=(0, bottom if bottom is not None else (0.04 if note else 0), 1, 1))
    fig.savefig(OUT / name)
    plt.close(fig)


def _plain_log_ticks(axis):
    """Label a log axis with plain numbers at 1-2-5 steps (20, 50, 100 ...), never as powers of ten."""
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
    axis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    axis.set_major_formatter(FuncFormatter(lambda v, _: "{:,.0f}".format(v) if v >= 1 else "{:g}".format(v)))
    axis.set_minor_formatter(NullFormatter())


def grouped(name, title, xlabel, groups, series, fmt="{:g}", note=None, log=False):
    """Horizontal grouped bars. groups: [(label, [v per series])]; series: [(name, color)]."""
    n = len(series)
    fig, ax = _axes(0.3 * n * len(groups) + 0.4 * len(groups) + 1.4 + (0.12 * n if n > 1 else 0), title, xlabel)
    vmax = max(max(v) for _, v in groups)
    if log:
        ax.set_xscale("log")
        ax.set_xlim(min(min(v) for _, v in groups) / 2, vmax * 4)
        _plain_log_ticks(ax.xaxis)
    else:
        ax.set_xlim(0, vmax * 1.2)
    h = 0.32
    ys = [i * (n * h + 0.45) for i in range(len(groups))][::-1]
    for y, (_, vals) in zip(ys, groups):
        for k, (v, (_, color)) in enumerate(zip(vals, series)):
            yy = y + (n - 1) * h / 2 - k * h
            left = ax.get_xlim()[0] if log else 0
            ax.barh(yy, v - left, left=left, height=h - 0.05, color=color, linewidth=0)
            ax.text(v * (1.06 if log else 1) + (0 if log else vmax * 0.012), yy, fmt.format(v),
                    va="center", color=INK, fontsize=9)
    ax.set_yticks(ys, [g[0] for g in groups])
    if n > 1:
        handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in series]
        names = [s for s, _ in series]
        ncol = n if sum(len(x) for x in names) < 70 else 1
        rows = -(-n // ncol)
        base = 0.035 if note else 0.0
        fig.legend(handles, names, loc="lower left", frameon=False, labelcolor=INK2, ncol=ncol,
                   bbox_to_anchor=(0.01, base))
        _save(fig, name, note, bottom=base + 0.045 * rows + 0.01)
    else:
        _save(fig, name, note)


def ranges(name, title, xlabel, rows, note=None, log=False):
    """rows: [(label, low, median, high)] as a floating bar with a median tick."""
    fig, ax = _axes(0.6 * len(rows) + 1.4, title, xlabel)
    hi_all = max(r[3] for r in rows)
    if log:
        ax.set_xscale("log")
        ax.set_xlim(min(r[1] for r in rows) / 2, hi_all * 40)
    else:
        ax.set_xlim(0, hi_all * 1.3)
    ys = list(range(len(rows)))[::-1]
    for y, (_, lo, med, hi) in zip(ys, rows):
        ax.barh(y, hi - lo if hi > lo else hi * 0.02, left=lo, height=0.45, color=BLUE, linewidth=0)
        ax.plot([med, med], [y - 0.3, y + 0.3], color=INK, linewidth=2)
        ax.text(hi * (1.08 if log else 1) + (0 if log else hi_all * 0.015), y,
                f"median {med:g} (range {lo:g}-{hi:g})", va="center", color=INK, fontsize=9)
    ax.set_yticks(ys, [r[0] for r in rows])
    _save(fig, name, note)


def lines(name, title, xlabel, ylabel, series, note=None, xticks=None):
    """series: [(label, color, [(x, y)])]; one y axis, direct labels at the line ends."""
    fig, ax = plt.subplots(figsize=(8.0, 4.2), dpi=150)
    ax.set_title(title, loc="left", color=INK, fontsize=12, pad=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for label, color, pts in series:
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=1.5, label=label)
    if xticks:
        ax.set_xticks(xticks)
    ax.legend(frameon=False, labelcolor=INK2, loc="best")
    _save(fig, name, note)


def main():
    OUT.mkdir(exist_ok=True)

    # Fig (X1/X2): host offloads, CPU per Gbps for traffic the unit terminates on the WAN port
    grouped("fig02-host-offloads.png",
            "TCP the unit terminates on its 2.5G WAN port: CPU per Gbps",
            "busy cores per Gbps (median of 5 runs, lower is better)",
            [("receive, all offloads on", [0.95]), ("receive, GRO off", [1.95]),
             ("send, all offloads on", [0.36]), ("send, TSO off", [0.67]), ("send, TX checksum off", [0.80])],
            [("Ethernet WAN, 4 connections", BLUE)], fmt="{:.2f}",
            note="receive with GRO: 1.72 Gbps; without: 0.88 Gbps; send with TSO + checksum: 2.35 Gbps")

    # Fig (X5): TCP through the NAT, 2.5G LAN port <-> 2.5G WAN port, 4 connections, median of 5
    grouped("fig05a-forwarding-throughput.png",
            "TCP through the NAT between the 2.5G ports, by forwarding path",
            "throughput at the egress port (Mbps, median of 5)",
            [("plain forwarding", [1619, 1038]), ("software flowtable", [2226, 1978]),
             ("PPE", [2476, 2478])],
            [("LAN to WAN", BLUE), ("WAN to LAN", ORANGE)],
            note="frame bytes from the unit's port counters; 4 TCP connections; 2.5G line rate is about 2470 Mbps")
    grouped("fig05b-forwarding-cpu.png",
            "Host CPU for the same traffic",
            "busy cores (of 2, median of 5)",
            [("plain forwarding", [1.39, 1.33]), ("software flowtable", [1.51, 1.48]),
             ("PPE", [0.005, 0.005])],
            [("LAN to WAN", BLUE), ("WAN to LAN", ORANGE)], fmt="{:.2f}",
            note="the software paths stop near 1.5 cores: all receive work runs on one core")

    # Fig (X1c): NAT over PPPoE between the 2.5G ports
    grouped("fig08-pppoe.png",
            "TCP through the NAT over PPPoE between the 2.5G ports",
            "throughput at the egress port (Mbps, median of 5)",
            [("plain forwarding, 1.3 cores", [1336, 999]), ("software flowtable, 1.3-1.5 cores", [1520, 1808]),
             ("PPE, 0.006 cores", [2361, 1937])],
            [("LAN to WAN", BLUE), ("WAN to LAN", ORANGE)],
            note="4 TCP connections; PPPoE server in kernel mode on the bench server; MTU 1492")

    # Fig (X6): 64-byte routed UDP LAN -> WAN, forwarded rate per path (log scale)
    grouped("fig06-small-packets.png",
            "64-byte UDP through the NAT: packets forwarded",
            "forwarded (kpps, log scale, median of 4-5 runs)",
            [("plain forwarding", [40, 50, 57]), ("software flowtable", [92, 111, 146]), ("PPE", [3075, 3725, 2690])],
            [("LAN to WAN, 3 x 1G ports, 3.0 Mpps offered", BLUE), ("LAN to WAN, 2.5G port, 3.7 Mpps offered", ORANGE),
             ("WAN to LAN, 2.5G WAN port, 2.69 Mpps offered", AQUA)],
            log=True, note="one-way UDP flows (1,500, 500 and 4,000); forwarded = the unit's egress transmit counters")

    # Fig (X8): host CPU with N flows bound in the PPE
    lines("fig07-flow-count.png",
          "Host CPU while the PPE carries N flows",
          "flows bound in the PPE", "busy cores",
          [("~100 pkt/s per flow, all bound", BLUE, [(0, 0.003), (300, 0.003), (1000, 0.014), (3000, 0.031), (6000, 0.075)])],
          xticks=[0, 1000, 3000, 6000],
          note="one-way UDP from three 1G LAN ports to the WAN; the flowtable reads every entry's statistics once a second")

    # Fig (X12): offloaded HTB on the first LAN port, download shaped, host CPU per path
    grouped("fig09-shaper.png",
            "Download shaped by the QDMA meter (htb offload): host CPU",
            "busy cores (median of 3; the rate holds within 2% on both paths)",
            [("100 Mbit class", [0.007, 0.47]), ("300 Mbit class", [0.007, 0.79]), ("600 Mbit class", [0.006, 1.04])],
            [("flow bound in the PPE", BLUE), ("plain forwarding", ORANGE)], fmt="{:.3g}",
            note="4 TCP connections from the WAN side to a host on the first LAN port; tc class 1:1 on eth0")

    # Fig (X13): EF and best effort into a 300 Mbit shaped port, loss per class
    grouped("fig10-priority.png",
            "EF and best effort into a 300 Mbit shaped port: loss per class",
            "packets lost (%, median of 3)",
            [("forwarded by the host", [45.7, 0.0]), ("bound in the PPE", [28.7, 35.8])],
            [("best effort, 300 Mbit offered", ORANGE), ("EF (DSCP 46), 200 Mbit offered", BLUE)], fmt="{:.1f}",
            note="UDP from the WAN side; default scheduler (strict priority between the 8 queues of the channel)")

    # Fig (X19): Wi-Fi client <-> WAN, host CPU per path (median of 3)
    grouped("fig14-wifi-cpu.png",
            "Wi-Fi 7 client through the NAT: host CPU per path",
            "busy cores (of 2, median of 3)",
            WIFI_CPU,
            [("download, TCP", BLUE), ("upload, TCP", ORANGE), ("download, 64-byte UDP", AQUA)], fmt="{:.2f}",
            note=WIFI_NOTE)

    # Fig (X29): AES-128-CBC through AF_ALG, one request in flight, by implementation and request size
    grouped("fig16-aes-cbc.png",
            "AES-128-CBC in the kernel, one request at a time",
            "MB/s (2 s per point)",
            [("256-byte requests", [27.8, 27.9, 18.5, 16.5]), ("1,408-byte requests", [37.1, 127.7, 38.2, 31.6]),
             ("8,192-byte requests", [91.2, 326.4, 46.5, 36.8])],
            [("EIP-93 (0.6-0.7 cores busy)", BLUE), ("ARMv8 crypto extensions (1 core)", ORANGE),
             ("NEON bit-sliced (1 core)", AQUA), ("generic C (1 core)", YELLOW)], fmt="{:.0f}",
            note="AF_ALG from user space; the EIP-93 driver hands requests up to 256 bytes to the CPU")

    trng_figure("fig17-trng.png")


def trng_figure(name):
    """Fig 19 (X32): raw TRNG samples vs the SHA-conditioned output, 4 MiB each, on shared scales."""
    import base64
    import json
    import numpy as np
    d = json.load(open(Path(__file__).resolve().parent / "data" / "trng.json"))
    rows = [("raw", "raw noise output (+0x828), as the Linux driver reads it"),
            ("sha", "SHA-conditioned output (+0x83C)")]
    fig = plt.figure(figsize=(10.5, 6.4), dpi=150)
    gs = fig.add_gridspec(2, 3, width_ratios=[1.6, 1.2, 0.75], hspace=0.55, wspace=0.3)
    hmax = max(max(d[k]["hist"]) for k, _ in rows) / (d["raw"]["bytes"] / 256)
    for r, (key, label) in enumerate(rows):
        s = d[key]
        exp = s["bytes"] / 256
        ratio = [c / exp for c in s["hist"]]
        ax = fig.add_subplot(gs[r, 0])
        ax.bar(range(256), ratio, width=1.0, color=BLUE if key == "raw" else AQUA, linewidth=0)
        ax.axhline(1.0, color=INK, linewidth=1)
        ax.set_ylim(0, hmax * 1.05)
        ax.set_xlim(-1, 256)
        ax.set_title("%s\nhow often each byte value occurs (1 = expected)" % label, loc="left", color=INK, fontsize=9.5)
        ax.set_xlabel("byte value")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax = fig.add_subplot(gs[r, 1])
        ac = s["autocorr"]
        ax.bar(range(1, len(ac) + 1), ac, color=ORANGE, linewidth=0)
        ax.axhline(0, color=INK2, linewidth=0.8)
        band = 3 / np.sqrt(s["bytes"])
        ax.axhspan(-band, band, color=GRID, zorder=0)
        ax.set_ylim(-0.05, 0.32)
        ax.set_title("correlation with the byte k places later\n(grey band: what pure chance gives)", loc="left",
                     color=INK, fontsize=9.5)
        ax.set_xlabel("k (bytes)")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax = fig.add_subplot(gs[r, 2])
        bits = np.unpackbits(np.frombuffer(base64.b64decode(s["bitmap_b64"]), dtype=np.uint8)).reshape(128, 128)
        ax.imshow(bits, cmap="Greys", interpolation="nearest")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title("first 16,384 bits", loc="left", color=INK, fontsize=9.5)
    _save(fig, name, note="4 MiB per source; rngtest FIPS 140-2: raw 0 of 1,000 blocks pass, conditioned 1,000 of 1,000; "
                          "min-entropy 5.16 vs 7.97 bits per byte")



if __name__ == "__main__":
    main()
