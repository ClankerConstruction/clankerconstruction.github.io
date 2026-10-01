#!/usr/bin/env python3
"""Figures and anonymised data for the CSI article.

usage: make_figures.py FEED RAW OUT

FEED  checkout of the feed with utils/csictl (samples, csiplot.py) and
      utils/icapctl (icapplot.py)
RAW   directory with the CSI/ICAP cross-check capture (xcsi.json, xcap.json;
      not shipped: the I/Q holds decodable MAC headers)
OUT   article directory; writes OUT/img/*.png and OUT/data/*
"""
import collections
import json
import lzma
import os
import re
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FEED, RAW, OUT = (os.path.abspath(a) for a in sys.argv[1:4])
sys.path.insert(0, os.path.join(FEED, "utils/csictl/scripts"))
sys.path.insert(0, os.path.join(FEED, "utils/icapctl/scripts"))
import csiplot as cp  # noqa: E402
import icapplot as ip  # noqa: E402

SAMPLES = os.path.join(FEED, "utils/csictl/samples")
IMG, DATA = os.path.join(OUT, "img"), os.path.join(OUT, "data")
for d in (IMG, DATA):
    os.makedirs(d, exist_ok=True)
plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.3})
MAC = re.compile(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b")
SUMMARY = {}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, name))
    plt.close(fig)
    print("wrote", name)


def sample(name):
    return cp.records(os.path.join(SAMPLES, name + ".json.xz"))


def sc_axis(n):
    return np.arange(n) - n // 2


def db(h):
    return 20 * np.log10(np.abs(h) + 1e-9)


def ppdus(recs):
    """Records grouped by PPDU (same transmitter, PPDU sequence, rx time)."""
    out, cur = [], []
    for r in recs:
        if cur and (cp.chain(r)[2] != cp.chain(cur[0])[2] or r["ta"] != cur[0]["ta"]):
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


# ---- figures ---------------------------------------------------------------

def fig_ppdu160(recs):
    n = cp.tones(recs)
    p = cp.first_ppdu(recs, n)
    sc = sc_axis(n)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for r in p:
        h = cp.cplx(r)
        a = db(h)
        a[np.abs(h) == 0] = np.nan
        tx, rx = r["trx_idx"] >> 16, r["trx_idx"] & 0xFFFF
        ax.plot(sc, a, lw=0.7, label="stream %d -> antenna %d" % (tx, rx))
    nulls = [int(s) for s, v in zip(sc, cp.cplx(p[0])) if v == 0]
    ax.set_xlabel("subcarrier (312.5 kHz)")
    ax.set_ylabel("|H| (dB, raw units)")
    ax.legend(fontsize=7, ncol=3)
    save(fig, "fig04-ppdu-160.png")
    groups = []
    for s in nulls:
        if groups and s - groups[-1][-1] == 1:
            groups[-1].append(s)
        else:
            groups.append([s])
    SUMMARY["null_tone_groups_160"] = [(g[0], g[-1]) for g in groups]
    SUMMARY["chains_160"] = len(p)


def fig_phase(recs):
    n = cp.tones(recs)
    sc = sc_axis(n)
    rs = [r for r in recs if cp.chain(r)[0] == 0][:8]
    fig, axs = plt.subplots(1, 2, figsize=(8, 3.4))
    for r in rs:
        h = cp.cplx(r)
        used = np.abs(h) > 0
        raw = np.full(n, np.nan)
        raw[used] = np.unwrap(np.angle(h[used]))
        axs[0].plot(sc, raw, lw=0.7)
        axs[1].plot(sc, cp.sanitise(h, sc), lw=0.7)
    axs[0].set_title("raw phase, 8 PPDUs, chain 0", fontsize=9)
    axs[1].set_title("after removing the linear fit", fontsize=9)
    for a in axs:
        a.set_xlabel("subcarrier")
    axs[0].set_ylabel("rad")
    save(fig, "fig06-phase.png")


def level_series(recs, chain0=True):
    t0 = recs[0]["rx_time"]
    t, lv, notch = [], [], []
    for r in recs:
        if chain0 and cp.chain(r)[0] != 0:
            continue
        a = np.hypot(np.array(r["i"], float), np.array(r["q"], float))
        used = a > 0
        d = 20 * np.log10(a[used])
        t.append((r["rx_time"] - t0) / 1e9)
        lv.append(d.mean())
        notch.append((d < np.median(d) - 10).any())
    return np.array(t), np.array(lv), np.array(notch)


def fig_levels(r24, r5):
    fig, axs = plt.subplots(2, 1, figsize=(8, 4.6), sharex=True)
    for ax, recs, name in ((axs[0], r24, "2.4 GHz EHT20"), (axs[1], r5, "5 GHz HE160")):
        t, lv, notch = level_series(recs)
        ax.plot(t, lv, ".", ms=2, label="record mean level")
        ax.plot(t[notch], lv[notch], "x", ms=4, color="C3",
                label="record with a notched tone (%d of %d)" % (notch.sum(), len(t)))
        ax.set_ylabel("dB (raw)")
        ax.set_title(name + ", chain 0, station still", fontsize=9)
        ax.legend(fontsize=7)
        steps = np.abs(np.diff(lv))
        SUMMARY["level_%s" % name.split()[0]] = {
            "records": int(len(t)), "notched": int(notch.sum()),
            "steps_gt_1db": int((steps > 1).sum()),
            "level_sd_db": round(float(lv.std()), 2)}
    axs[1].set_xlabel("time (s)")
    save(fig, "fig08-levels.png")


def stability(recs):
    n = cp.tones(recs)
    sc = sc_axis(n)
    amp, ph = [], []
    for r in recs:
        if cp.chain(r)[0] != 0 or len(r["i"]) != n:
            continue
        h = cp.cplx(r)
        if not (np.abs(h) > 0).any():
            continue
        a = db(h)
        a[np.abs(h) == 0] = np.nan
        amp.append(a - np.nanmean(a))
        ph.append(cp.sanitise(h, sc))
    amp, ph = np.array(amp), np.array(ph)
    med = np.nanmedian(amp, axis=0)
    ok = (np.nan_to_num(np.abs(amp - med), nan=0) < 10).all(axis=1)
    return sc, np.nanstd(amp[ok], axis=0), np.nanstd(ph[ok], axis=0)


def fig_stability(r24, r5):
    fig, axs = plt.subplots(1, 2, figsize=(8, 3.4))
    for recs, name in ((r24, "2.4 GHz"), (r5, "5 GHz")):
        sc, a, p = stability(recs)
        x = sc / (len(sc) / 2)
        axs[0].plot(x, a, lw=0.8, label=name)
        axs[1].plot(x, p, lw=0.8, label=name)
        SUMMARY["stability_" + name] = {"amp_sd_db_median": round(float(np.nanmedian(a)), 3),
                                        "phase_sd_rad_median": round(float(np.nanmedian(p)), 4)}
    axs[0].set_title("amplitude s.d. over 30 s (dB)", fontsize=9)
    axs[1].set_title("sanitised phase s.d. over 30 s (rad)", fontsize=9)
    for a in axs:
        a.set_xlabel("position in the band (-1 .. 1)")
        a.legend(fontsize=7)
    save(fig, "fig07-stability.png")


def fig_timing(r24, r5):
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    for recs, name in ((r24, "2.4 GHz, ping"), (r5, "5 GHz, 1 Mb/s upload")):
        t = np.array(sorted({p[0]["rx_time"] for p in ppdus(recs)})) / 1e6
        d = np.diff(t)
        ax.hist(np.clip(d, 0, 300), bins=np.arange(0, 301, 5), alpha=0.6,
                label="%s: %d PPDUs, median %.0f ms" % (name, len(t), np.median(d)))
        SUMMARY["timing_" + name] = {"ppdus": int(len(t)), "median_ms": round(float(np.median(d)), 1),
                                     "p90_ms": round(float(np.percentile(d, 90)), 1),
                                     "rate_per_s": round(float(len(t) / ((t[-1] - t[0]) / 1e3)), 1)}
    ax.set_xlabel("time between PPDUs with CSI (ms, clipped at 300)")
    ax.set_ylabel("count")
    ax.legend(fontsize=7)
    save(fig, "fig05-timing.png")


def xcheck():
    """CSI (RX antenna 0) against the L-LTF channel from ICAP (RX path 0),
    same station and frames, legacy 24 Mb/s."""
    k = [i for i in range(-26, 27) if i]
    csi = [json.loads(l) for l in open(os.path.join(RAW, "xcsi.json")) if l.startswith("{")]
    ta = collections.Counter(r["ta"] for r in csi).most_common(1)[0][0]
    c = np.array([[complex(r["i"][i % 64], r["q"][i % 64]) for i in k] for r in csi])
    h, snr = [], []
    for line in open(os.path.join(RAW, "xcap.json")):
        if not line.startswith("{"):
            continue
        x = ip.to_20msps(json.loads(line))
        for s in ip.detect_ppdus(x):
            r = ip.demod_ppdu(x, s)
            if not r or r.get("fmt") != "legacy" or r.get("mbps") != 24:
                continue
            if r.get("ta") not in (ta, None):
                continue
            ltf, cfo = ip.sync_ltf(x, s)
            est, sn = ip.channel_legacy(x, ltf, cfo)
            h.append([est[i] for i in k])
            snr.append(sn)
    h = np.array(h)

    def norm(m):
        d = db(m)
        return d - d.mean(axis=1, keepdims=True)

    def san(m):
        out = []
        for row in m:
            ph = np.unwrap(np.angle(row))
            out.append(ph - np.polyval(np.polyfit(k, ph, 1), k))
        return np.array(out)

    cd, idb = norm(c), norm(h)
    cph, iph = san(c), san(h)
    fig, axs = plt.subplots(1, 2, figsize=(8, 3.6))
    for m, name in ((cd, "CSI, %d records" % len(cd)), (idb, "ICAP L-LTF, %d PPDUs" % len(idb))):
        mu, sd = m.mean(0), m.std(0)
        axs[0].plot(k, mu, label=name)
        axs[0].fill_between(k, mu - sd, mu + sd, alpha=0.2)
    for m, name in ((cph, "CSI"), (iph, "ICAP")):
        axs[1].plot(k, m.mean(0), label=name)
    axs[0].set_title("|H| shape (mean removed), +/- 1 s.d.", fontsize=9)
    axs[1].set_title("sanitised phase, mean", fontsize=9)
    for a in axs:
        a.set_xlabel("subcarrier")
        a.legend(fontsize=7)
    axs[0].set_ylabel("dB")
    axs[1].set_ylabel("rad")
    save(fig, "fig09-csi-vs-icap.png")
    mc, mi = cd.mean(0), idb.mean(0)
    inner = np.abs(np.array(k)) <= 20
    SUMMARY["xcheck"] = {
        "csi_records": int(len(cd)), "icap_ppdus": int(len(idb)),
        "amp_corr": round(float(np.corrcoef(mc, mi)[0, 1]), 3),
        "amp_rms_diff_db": round(float(np.sqrt(np.mean((mc - mi) ** 2))), 2),
        "amp_rms_diff_inner_db": round(float(np.sqrt(np.mean(((mc - mc[inner].mean()) - (mi - mi[inner].mean()))[inner] ** 2))), 2),
        "edge_rolloff_db": {"csi": round(float(mc[:3].mean() - mc[inner].mean()), 2),
                            "icap": round(float(mi[:3].mean() - mi[inner].mean()), 2)},
        "phase_corr": round(float(np.corrcoef(cph.mean(0), iph.mean(0))[0, 1]), 3),
        "phase_rms_diff_rad": round(float(np.sqrt(np.mean((cph.mean(0) - iph.mean(0)) ** 2))), 4),
        "amp_sd_per_tone_db": {"csi": round(float(cd.std(0).mean()), 2),
                               "icap": round(float(idb.std(0).mean()), 2)},
        "snr_db_median": {"csi": float(np.median([r["snr"] for r in csi if r["snr"] is not None])),
                          "icap_lltf": round(float(np.median(snr)), 1)},
        "rssi_dbm": sorted(collections.Counter(r["rssi"] for r in csi).items()),
        "tr_stream": sorted(collections.Counter(r["tr_stream"] for r in csi).items()),
    }
    # anonymised CSI records of this run
    with lzma.open(os.path.join(DATA, "2g-legacy-xcheck.json.xz"), "wt") as o:
        for r in csi:
            o.write(MAC.sub("02:00:00:00:00:01", json.dumps(r)) + "\n")
    with open(os.path.join(DATA, "xcheck-profiles.csv"), "w") as o:
        o.write("subcarrier,csi_db,icap_db,csi_phase_rad,icap_phase_rad\n")
        for i, s in enumerate(k):
            o.write("%d,%.3f,%.3f,%.4f,%.4f\n" % (s, mc[i], mi[i], cph.mean(0)[i], iph.mean(0)[i]))


def waterfall(ax, recs, title, vmax=6):
    n = cp.tones(recs)
    rows, t0 = [], recs[0]["rx_time"]
    for r in recs:
        if cp.chain(r)[0] != 0 or len(r["i"]) != n:
            continue
        a = db(cp.cplx(r))
        rows.append(a - np.median(a))
    m = np.array(rows)
    m -= np.median(m, axis=0)
    dur = (recs[-1]["rx_time"] - t0) / 1e9
    ax.imshow(m.T, aspect="auto", origin="lower", cmap="RdBu_r", vmin=-vmax, vmax=vmax,
              extent=[0, dur, -n // 2, n // 2], interpolation="nearest")
    ax.set_title(title, fontsize=9)
    ax.set_ylabel("subcarrier")


def fig_waterfalls(still, walk):
    fig, axs = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    waterfall(axs[0], still, "5 GHz, chain 0, station still: deviation from the median (dB)")
    waterfall(axs[1], walk, "5 GHz, chain 0, a person walking")
    axs[1].set_xlabel("time (s)")
    save(fig, "fig10-waterfalls.png")


def fig_motion(sets):
    fig, axs = plt.subplots(1, 2, figsize=(8, 3.4), sharey=False)
    for ax, (band, still, walk) in zip(axs, sets):
        for recs, name, col in ((still, "still", "C0"), (walk, "walking", "C3")):
            t, s, _ = cp.score(recs, 1.0)
            ax.plot(t, s, "o-", ms=3, color=col, label=name)
            SUMMARY.setdefault("motion", {})["%s %s" % (band, name)] = {
                "median": round(float(np.median(s)), 3), "p90": round(float(np.percentile(s, 90)), 3),
                "min": round(float(s.min()), 3), "max": round(float(s.max()), 3), "windows": int(len(s))}
        ax.set_title(band, fontsize=9)
        ax.set_xlabel("time (s)")
        ax.set_ylabel("motion score (dB)")
        ax.legend(fontsize=7)
    save(fig, "fig11-motion.png")


def main():
    r24s, r24w = sample("2g-still"), sample("2g-walk")
    r5s, r5w = sample("5g-still"), sample("5g-walk")
    fig_ppdu160(r5s)
    fig_phase(r5s)
    fig_levels(r24s, r5s)
    fig_stability(r24s, r5s)
    fig_timing(r24s, r5s)
    xcheck()
    fig_waterfalls(r5s, r5w)
    fig_motion([("5 GHz HE160", r5s, r5w), ("2.4 GHz EHT20", r24s, r24w)])
    with open(os.path.join(DATA, "summary.json"), "w") as o:
        json.dump(SUMMARY, o, indent=1)
    print(json.dumps(SUMMARY, indent=1))


if __name__ == "__main__":
    main()
