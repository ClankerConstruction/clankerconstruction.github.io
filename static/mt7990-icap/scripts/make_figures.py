#!/usr/bin/env python3
"""Figures and anonymised data for the ICAP article.

usage: make_figures.py CAPTURES FEED OUT

CAPTURES  directory with the raw capture files (JSON lines from
          `icapctl capture`; not shipped, see the article, section 12)
FEED      checkout of the feed that holds utils/icapctl (decoder sources)
OUT       article directory; writes OUT/img/*.png and OUT/data/*

Every MAC address in the written data is replaced by a placeholder,
numbered by how often the address occurs over all decoded captures.
"""
import collections
import glob
import json
import math
import os
import re
import subprocess
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CAP, FEED, OUT = (os.path.abspath(a) for a in sys.argv[1:4])
SRC = os.path.join(FEED, "utils/icapctl/src")
sys.path.insert(0, os.path.join(FEED, "utils/icapctl/scripts"))
import icapplot as ip  # noqa: E402

WORK = os.path.join(os.path.dirname(CAP), "work")
IMG, DATA = os.path.join(OUT, "img"), os.path.join(OUT, "data")
for d in (WORK, IMG, DATA):
    os.makedirs(d, exist_ok=True)

plt.rcParams.update({"figure.dpi": 110, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.3})
MAC = re.compile(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b")
CELL = {1: -4.8, 2: -4.8, 4: -11.8, 6: -18.0, 8: -24.1, 10: -30.1, 12: -36.1}
NBPSC = {"BPSK": 1, "QPSK": 2, "16-QAM": 4, "64-QAM": 6, "256-QAM": 8,
         "1024-QAM": 10}


# ---- C analyzer over the raw captures ----------------------------------

def analyzer():
    exe = os.path.join(WORK, "icap-analyze")
    srcs = [os.path.join(SRC, f) for f in ("icap_agent.c", "icap_report.c",
                                           "icap_phy.c", "icap_dsp.c")]
    subprocess.run(["gcc", "-std=gnu11", "-D_GNU_SOURCE", "-O2", "-I", SRC,
                    "-o", exe, os.path.join(OUT, "scripts/analyze_main.c")]
                   + srcs + ["-lm"], check=True)
    return exe


def decode(exe, name, *opts):
    out = os.path.join(WORK, name + ".jsonl")
    src = os.path.join(CAP, name + ".json")
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        with open(src) as i, open(out, "w") as o:
            subprocess.run([exe] + list(opts), stdin=i, stdout=o, check=True)
    return [json.loads(l) for l in open(out)]


def caps(name):
    return [json.loads(l) for l in open(os.path.join(CAP, name + ".json"))
            if l.startswith("{")]


# ---- anonymisation ---------------------------------------------------------

class Anon:
    def __init__(self, texts):
        n = collections.Counter(m for t in texts for m in MAC.findall(t))
        self.map = {m: "02:00:00:00:%02x:%02x" % divmod(i + 1, 256)
                    for i, (m, _) in enumerate(n.most_common())}

    def __call__(self, text):
        return MAC.sub(lambda m: self.map.get(m.group(0), "02:00:00:00:ff:ff"),
                       text)

    def name(self, mac):
        return self(mac)


def ppdus(recs):
    return [r for r in recs if r["type"] == "ppdu"]


def lin_mean_db(v):
    return 10 * math.log10(np.mean([10 ** (e / 10) for e in v])) if v else float("nan")


# ---- figures ---------------------------------------------------------------

def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, name))
    plt.close(fig)
    print("wrote", name)


def symbol_marks(x, stf, count=40):
    """FFT starts of the legacy data symbols of the PPDU at stf, with the
    guard match and the symbol power (dBFS) of each."""
    r = ip.demod_ppdu(x, stf)
    t = r["ltf"] + 128 + 16
    out = []
    for m in range(count):
        ts = t + 80 * (m + 1)
        if ts + 64 > len(x):
            break
        p = np.mean(np.abs(x[ts:ts + 64]) ** 2)
        out.append((ts, ip.cp_match(x, ts), 10 * np.log10(p / 8192 ** 2 + 1e-12)))
    return r, out


def fig_window(leg12, dl, dl_idx):
    fig, axs = plt.subplots(2, 1, figsize=(8, 5.6), sharex=True)
    # (a) free-running window: fresh part, gain step, older samples
    c = leg12
    x = ip.to_20msps(c)
    stf = ip.detect_ppdus(x)[0]
    r, marks = symbol_marks(x, stf)
    t = np.arange(len(x)) / 20
    p = 10 * np.log10(np.convolve(np.abs(x) ** 2, np.ones(16) / 16, "same")
                      / 8192 ** 2 + 1e-12)
    ax = axs[0]
    ax.plot(t, p, lw=0.6, color="C0", label="power, 16-sample mean")
    fresh = next((i for i, m in enumerate(marks) if m[1] < ip.CP_MIN), len(marks))
    ax.axvline(stf / 20, color="k", ls=":", lw=0.8)
    ax.text(stf / 20 + 0.5, p.max() - 3, "L-STF", fontsize=8)
    if fresh < len(marks):
        tb = (marks[fresh][0] - 16) / 20
        ax.axvspan(tb, t[-1], color="C3", alpha=0.08)
        ax.text(tb + 0.5, p.max() - 3, "older samples", color="C3", fontsize=8)
    ax.set_ylabel("dBFS")
    ax2 = ax.twinx()
    ax2.grid(False)
    ax2.bar([(m[0] - 16) / 20 + 2 for m in marks], [m[1] for m in marks],
            width=3.2, color=["C2" if i < fresh else "C3" for i in range(len(marks))],
            alpha=0.5, label="guard match per data symbol")
    ax2.axhline(ip.CP_MIN, color="C2", ls="--", lw=0.8)
    ax2.set_ylim(0, 1.05)
    ax2.set_ylabel("guard-interval match")
    ax.set_title("(a) free-running window: %d fresh data symbols, then older capture memory"
                 % fresh, fontsize=9)
    # (b) window armed during own transmission: the response fills it
    x = ip.to_20msps(dl)
    p = 10 * np.log10(np.convolve(np.abs(x) ** 2, np.ones(16) / 16, "same")
                      / 8192 ** 2 + 1e-12)
    ax = axs[1]
    ax.plot(t, p, lw=0.6, color="C0")
    for s in ip.detect_ppdus(x):
        ax.axvline(s / 20, color="k", ls=":", lw=0.8)
        ax.text(s / 20 + 0.5, p.max() - 3, "response PPDU", fontsize=8)
    ax.set_ylabel("dBFS")
    ax.set_xlabel("time in window (us)")
    ax.set_title("(b) window armed while the AP transmitted: the peer's Block Ack, "
                 "fresh to the end", fontsize=9)
    save(fig, "fig03-window.png")
    return fresh


def fig_pair(c):
    iq = np.asarray(c["iq"], float)
    raw = iq[0::2] + 1j * iq[1::2]
    fixed = ip.to_20msps(c)
    fig, axs = plt.subplots(1, 2, figsize=(8, 4))
    out = {}
    for ax, x, name in ((axs[0], raw, "as captured"),
                        (axs[1], fixed, "after the pair repair")):
        best = None
        for s in ip.detect_ppdus(x):
            r = ip.demod_ppdu(x, s)
            if r and r.get("nbpsc") and len(r["points"]):
                best = r
                break
        if best is None:
            ax.set_title(name + ": no PPDU decoded", fontsize=9)
            continue
        pts = np.asarray(best["points"])
        ip.constellation(ax, best["nbpsc"], pts, "")
        out[name] = best["evm_db"]
        ax.set_title("%s: %s, EVM %.1f dB" % (name, ip.MOD_NAME[best["nbpsc"]],
                                             best["evm_db"]), fontsize=9)
    save(fig, "fig02-pair-repair.png")
    return out


def fig_evm_rate(sets):
    fig, ax = plt.subplots(figsize=(8, 3.8))
    labels, pos = [], 0
    for label, recs, mod in sets:
        v = [r["evm_db"] for r in recs if r.get("mod") == mod
             and r.get("evm_db") is not None]
        if not v:
            continue
        ax.scatter(np.full(len(v), pos) + np.random.default_rng(pos).uniform(
            -0.18, 0.18, len(v)), v, s=6, alpha=0.5)
        ax.plot([pos - 0.3, pos + 0.3], [lin_mean_db(v)] * 2, color="k", lw=1.5)
        g = CELL[NBPSC[mod]] - 3
        ax.plot([pos - 0.4, pos + 0.4], [g, g], color="C3", lw=1.2, ls="--")
        labels.append("%s\n%s\n(%d)" % (label, mod, len(v)))
        pos += 1
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("EVM per PPDU (dB)")
    ax.set_ylim(-36, -4)
    ax.plot([], [], color="k", label="mean (power average)")
    ax.plot([], [], color="C3", ls="--", label="grid-resolved gate (cell EVM - 3 dB)")
    ax.legend(loc="upper right", fontsize=7)
    save(fig, "fig08-evm-per-rate.png")


def fig_gain(gsets):
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    xs, lev, snr, evm, he = [], [], [], [], []
    for g, recs in gsets:
        leg = [r for r in recs if r["fmt"] == "legacy" and r.get("fcs") == 1]
        xs.append(g)
        lev.append(np.median([r["power_dbfs"] for r in leg]))
        snr.append(np.median([r["snr_db"] for r in leg]))
        evm.append(lin_mean_db([r["evm_db"] for r in leg if r.get("evm_db") is not None]))
        he.append(lin_mean_db([r["evm_db"] for r in recs if r["fmt"] == "HE-data"
                               and r.get("evm_db") is not None]))
    names = ["AGC" if g == 0 else str(g) for g in xs]
    ax.plot(names, lev, "o-", label="legacy level (dBFS)")
    ax.plot(names, [-s for s in snr], "s-", label="- L-LTF SNR (dB)")
    ax.plot(names, evm, "^-", label="legacy EVM (dB)")
    ax.plot(names, he, "v-", label="HE-MCS 10 data EVM (dB)")
    ax.set_xlabel("receive gain setting (0 = AGC, 1 high .. 7 low)")
    ax.set_ylabel("dB")
    ax.legend(fontsize=7)
    save(fig, "fig13-gain.png")
    return list(zip(names, lev, snr, evm, he))


def floor_fit(snr, evm):
    snr, evm = np.asarray(snr), np.asarray(evm)
    best = None
    for f in np.arange(-40, -20, 0.1):
        model = 10 * np.log10(10 ** (-snr / 10) + 10 ** (f / 10))
        e = np.mean((model - evm) ** 2)
        if best is None or e < best[1]:
            best = (f, e)
    return best[0]


def fig_evm_snr(points, extra=None):
    fig, ax = plt.subplots(figsize=(6.5, 4))
    snr = [p[0] for p in points]
    evm = [p[1] for p in points]
    ax.scatter(snr, evm, s=5, alpha=0.4, label="legacy PPDUs, FCS good")
    if extra:
        ax.scatter([p[0] for p in extra], [p[1] for p in extra], s=8, alpha=0.6,
                   color="C1", label="8 repeat runs, 24 Mb/s")
        snr += [p[0] for p in extra]
        evm += [p[1] for p in extra]
    f = floor_fit(snr, evm)
    s = np.linspace(min(snr) - 2, max(snr) + 2, 100)
    ax.plot(s, -s, color="k", ls=":", lw=0.8, label="EVM = -SNR")
    ax.plot(s, 10 * np.log10(10 ** (-s / 10) + 10 ** (f / 10)), color="C3",
            label="-SNR with a %.1f dB floor" % f)
    ax.set_xlabel("L-LTF SNR (dB)")
    ax.set_ylabel("EVM (dB)")
    ax.set_ylim(-36, -10)
    ax.legend(fontsize=7)
    save(fig, "fig12-evm-snr.png")
    return f


def fig_cfo(groups, anon):
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    for i, (ta, v) in enumerate(groups):
        ax.hist(v, bins=np.arange(-12, 12, 0.25), alpha=0.6,
                label="station %s (%d PPDUs, %.2f kHz s.d.)"
                % ("AB"[i], len(v), np.std(v)))
    ax.set_xlabel("carrier offset against the AP (kHz, 2.4 GHz)")
    ax.set_ylabel("PPDUs")
    ax.legend(fontsize=7)
    save(fig, "fig07-cfo.png")


def fig_channel(x, stf):
    r = ip.sync_ltf(x, stf)
    ltf, cfo = r
    h, snr = ip.channel_legacy(x, ltf, cfo)
    k = sorted(h)
    fig, ax = plt.subplots(figsize=(6.5, 3))
    db = np.array([20 * np.log10(abs(h[i]) + 1e-9) for i in k])
    ax.plot(k, db, "o-", ms=3)
    lo = [k[i] for i in range(1, len(k) - 1)
          if db[i] < db[i - 1] and db[i] < db[i + 1] and db[i] < db.max() - 10]
    for n in lo:
        ax.axvline(n, color="C3", ls=":", lw=0.8)
    if len(lo) > 1:
        ax.set_title("notches at subcarriers %s: every %d tones (%.2f MHz)"
                     % (", ".join(map(str, lo)), lo[1] - lo[0],
                        (lo[1] - lo[0]) * 0.3125), fontsize=9)
    ax.set_xlabel("subcarrier")
    ax.set_ylabel("|H| (dB, relative)")
    save(fig, "fig14-channel.png")


def fig_unresolved(name, nbpsc_mod=10):
    he = {}
    pts = []
    for c in caps(name):
        for r in ip.analyse(ip.to_20msps(c), he):
            if r.get("fmt") == "HE-data" and r.get("nbpsc") == nbpsc_mod:
                pts.append(np.asarray(r["points"]))
    if not pts:
        return None
    p = np.concatenate(pts)
    fig, ax = plt.subplots(figsize=(4.6, 4.6))
    e = ip.evm_db(p, nbpsc_mod)
    ip.constellation(ax, nbpsc_mod, p, "")
    ax.set_title("HE-MCS 10, 1024-QAM, %d PPDUs, EVM %.1f dB:\ncells not resolved"
                 % (len(pts), e), fontsize=9)
    save(fig, "fig10-1024qam-unresolved.png")
    return len(pts), e


def fig_4096(evm_in=-42.0):
    """Synthetic 4096-QAM at a known EVM: the page resolves 64 x 64 cells."""
    rng = np.random.default_rng(12)
    grid = ip.qam_grid(12)
    ideal = grid[rng.integers(0, len(grid), 30000)]
    sigma = 10 ** (evm_in / 20) / np.sqrt(2)
    pts = ideal + sigma * (rng.standard_normal(len(ideal)) +
                           1j * rng.standard_normal(len(ideal)))
    e = ip.evm_db(pts, 12)
    ip.constellation_page(os.path.join(IMG, "fig11-4096qam-synthetic.png"), 12,
                          pts, "synthetic 4096-QAM, %d points, set %.0f dB, "
                          "measured %.1f dB" % (len(pts), evm_in, e))
    print("wrote fig11-4096qam-synthetic.png")
    return e


# ---- synthetic capture -----------------------------------------------------

def synthetic(path):
    """A legacy 16-QAM data frame through a two-path channel, sampled the
    way the capture engine delivers it (odd samples half a period late)."""
    sys.path.insert(0, os.path.join(FEED, "utils/icapctl/scripts"))
    import test_icapplot as t

    rng = np.random.default_rng(7)
    ta = [0x02, 0, 0, 0, 0, 0x01]
    ra = [0x02, 0, 0, 0, 0, 0x10]
    body = [0x88, 0x01, 0, 0] + ra + ta + ra + [0x10, 0, 0, 0]
    body += list(rng.integers(0, 256, 60))
    import zlib
    psdu = body + list(zlib.crc32(bytes(body)).to_bytes(4, "little"))
    bits = [0] * 16
    for o in psdu:
        bits += [(int(o) >> i) & 1 for i in range(8)]
    ndbps = 96
    nsym = -(-(len(bits) + 6) // ndbps)
    bits += [0] * (nsym * ndbps - len(bits))
    sbits = t.scramble(bits)
    tail = 16 + 8 * len(psdu)
    sbits[tail:tail + 6] = [0] * 6
    coded = t.puncture(t.conv(sbits), "1/2")
    x = t.channel(t.legacy_ppdu(0b1001, len(psdu), coded=coded), 32, 4e3, rng)
    x = np.concatenate((x, np.zeros(2048)))[:2048]
    # the engine's view: sample n at time n for even n, n - 0.5 for odd n
    f = np.fft.fftfreq(2048)
    late = np.fft.ifft(np.fft.fft(x) * np.exp(-1j * np.pi * f))
    y = x.copy()
    y[1::2] = late[1::2]
    y *= 3000 / np.sqrt(np.mean(np.abs(y) ** 2))
    iq = np.empty(4096, int)
    iq[0::2] = np.round(y.real)
    iq[1::2] = np.round(y.imag)
    with open(path, "w") as o:
        o.write(json.dumps({"band": 0, "node": 0x00204000, "bw": 0,
                            "rx_time": 0, "iq": iq.tolist()}) + "\n")


def main():
    exe = analyzer()
    names = ["leg6", "leg12", "leg24", "all-he4", "he5", "he6", "he7",
             "all-he8", "all-he9", "he10", "he11", "he10g1", "he10g3",
             "he10g5", "he10g7", "dl", "he79", "ehtu"]
    dec = {n: decode(exe, n) for n in names}
    anon = Anon([json.dumps(r) for n in names for r in dec[n]])

    # figure 3: anatomy of windows
    leg12 = caps("leg12")
    dl = caps("dl")
    li = next(r["t"] - 1 for r in ppdus(dec["leg12"])
              if r.get("frame") == "qos-data" and r["pos"] > 200)
    di = next(r["t"] - 1 for r in ppdus(dec["dl"]) if r.get("frame") == "BA"
              and 230 < r["pos"] < 270)
    fresh = fig_window(leg12[li], dl[di], di)

    # figure 4: pair repair on a 16-QAM RTS
    ri = next(r["t"] - 1 for r in ppdus(dec["leg24"]) if r.get("frame") == "RTS"
              and r.get("fcs") == 1)
    pair = fig_pair(caps("leg24")[ri])

    # figure 7: EVM per rate
    sets = [("legacy 6", ppdus(dec["leg6"]), "BPSK"),
            ("legacy 12", ppdus(dec["leg12"]), "QPSK"),
            ("legacy 24", ppdus(dec["leg24"]), "16-QAM"),
            ("HE-MCS 4", [r for r in ppdus(dec["all-he4"]) if r["fmt"] == "HE-data"], "16-QAM"),
            ("HE-MCS 5-7", [r for n in ("he5", "he6", "he7") for r in ppdus(dec[n])
                            if r["fmt"] == "HE-data"], "64-QAM"),
            ("HE-MCS 8", [r for r in ppdus(dec["all-he8"]) if r["fmt"] == "HE-data"], "256-QAM"),
            ("HE-MCS 9", [r for r in ppdus(dec["all-he9"]) if r["fmt"] == "HE-data"], "256-QAM"),
            ("HE-MCS 10-11", [r for n in ("he10", "he11") for r in ppdus(dec[n])
                              if r["fmt"] == "HE-data"], "1024-QAM")]
    for i, (l, recs, mod) in enumerate(sets[:3]):
        sets[i] = (l, [r for r in recs if r.get("rate_mbps") == int(l.split()[1])
                       and r.get("evm_db") is not None and r["evm_db"] < -15], mod)
    fig_evm_rate(sets)

    # figure 8: fixed gain
    gain = fig_gain([(0, ppdus(dec["he10"]))] +
                    [(g, ppdus(dec["he10g%d" % g])) for g in (1, 3, 5, 7)])

    # figure 9: EVM vs SNR over every good legacy frame of the bench station
    pts = [(r["snr_db"], r["evm_db"]) for n in names if n not in ("dl", "ehtu")
           for r in ppdus(dec[n]) if r["fmt"] == "legacy" and r.get("fcs") == 1
           and r.get("evm_db") is not None and r.get("snr_db") is not None]
    extra = None
    tx = sorted(glob.glob(os.path.join(CAP, "txp*.json")))
    if tx:
        extra = []
        for f in tx:
            n = os.path.basename(f)[:-5]
            extra += [(r["snr_db"], r["evm_db"]) for r in ppdus(decode(exe, n))
                      if r["fmt"] == "legacy" and r.get("fcs") == 1
                      and r.get("evm_db") is not None
                      and r.get("rate_mbps") == 24]
    floor = fig_evm_snr(pts, extra)

    # figure 10: carrier offset per named source
    by = collections.defaultdict(list)
    for n in names:
        for r in ppdus(dec[n]):
            if r.get("ta") and (r.get("fcs") == 1 or
                                (r.get("evm_db") or 0) < -15):
                by[r["ta"]].append(r["cfo_khz"])
    groups = sorted(by.items(), key=lambda kv: -len(kv[1]))[:2]
    fig_cfo(groups, anon)

    # figure 11: channel of the two-antenna client (Block Ack)
    x = ip.to_20msps(dl[di])
    fig_channel(x, ip.detect_ppdus(x)[0])

    # figure 6g: 1024-QAM at the floor; 6h: 4096-QAM rendering check
    unres = fig_unresolved("he10")
    syn4096 = fig_4096()

    # data: anonymised PPDU lines and a monitor report
    keep, seen = [], set()
    for n in ("leg24", "all-he8", "he79", "ehtu", "dl"):
        for r in ppdus(dec[n]):
            k = (r["fmt"], r.get("frame"), r.get("mod"))
            if k in seen or (r["fmt"] == "legacy" and r.get("fcs") != 1
                             and r.get("frame") != "qos-data"):
                continue
            seen.add(k)
            keep.append(anon(json.dumps(r)))
    with open(os.path.join(DATA, "ppdu-examples.jsonl"), "w") as o:
        o.write("\n".join(keep[:24]) + "\n")
    mon = os.path.join(os.path.dirname(CAP), "reports", "mon2.jsonl")
    if os.path.exists(mon):
        reps = [l for l in open(mon) if '"type":"report"' in l]
        best = max(reps, key=lambda l: l.count("256-QAM"))
        with open(os.path.join(DATA, "monitor-report.json"), "w") as o:
            json.dump(json.loads(anon(best)), o, indent=1)
            o.write("\n")
    with open(os.path.join(DATA, "sweep-summary.csv"), "w") as o:
        o.write("set,modulation,ppdus,mean_evm_db,best_evm_db,gate_db\n")
        for l, recs, mod in sets:
            v = [r["evm_db"] for r in recs if r.get("mod") == mod
                 and r.get("evm_db") is not None]
            if v:
                o.write("%s,%s,%d,%.2f,%.2f,%.1f\n" % (l, mod, len(v), lin_mean_db(v),
                                                     min(v), CELL[NBPSC[mod]] - 3))
    synthetic(os.path.join(DATA, "synthetic-capture.json"))
    with open(os.path.join(DATA, "synthetic-capture.json")) as i:
        r = subprocess.run([exe], stdin=i, capture_output=True, text=True).stdout
    with open(os.path.join(DATA, "synthetic-decoded.jsonl"), "w") as o:
        o.write(r)

    summary = {"fresh_symbols_fig3": fresh, "pair_repair_evm": pair,
               "gain": gain, "floor_db": floor, "unresolved_1024": unres,
               "synthetic_4096_evm": syn4096,
               "legacy_points": len(pts),
               "cfo": [(anon.name(t), len(v), float(np.mean(v)), float(np.std(v)))
                       for t, v in groups]}
    with open(os.path.join(WORK, "summary.json"), "w") as o:
        json.dump(summary, o, indent=1, default=str)
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
