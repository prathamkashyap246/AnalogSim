"""
plot_validation.py -- Overlay plots of AnalogSim vs ngspice (validation figures for the README).

Run:  python plot_validation.py            (from apps/api; needs ngspice on PATH and matplotlib)
Writes: ../../docs/validation-ac-common-source.png
        ../../docs/validation-dc-inverter-vtc.png

Both simulators run the same circuits with the same device parameters. LAMBDA=0 on both sides because
ngspice LEVEL1 applies channel-length modulation in triode as well, while this project applies it in
saturation only (documented design choice); with LAMBDA=0 any remaining difference is numerical.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from app.engines.circuit import Circuit
from app.engines.netlist_parser import parse_netlist_full
from app.engines.non_ideal_engine import mosfet_constants

# ngspice's default RELTOL (1e-3) is ~1.8 mV on a 1.8 V rail -- looser than the agreement being measured --
# so both decks run with tight tolerances. (With the defaults the inverter curve differs by up to 0.4 mV,
# on the near-vertical switching edge; with these options the difference is a few nanovolts, i.e. floating-point noise.)
TIGHT = ".options reltol=1e-9 vntol=1e-12 abstol=1e-15\n"

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs"))
ACCENT, SPICE = "#b5541f", "#1f6f6a"


def ngspice(deck: str, control: str) -> np.ndarray:
    """Run a deck in batch mode and return the wrdata table."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.txt").replace("\\", "/")
        path = os.path.join(tmp, "deck.cir")
        open(path, "w").write(f"{deck}\n.control\nset units=degrees\n{control.format(out=out)}\n.endc\n.end\n")
        subprocess.run(["ngspice", "-b", path], check=True, capture_output=True, text=True)
        return np.loadtxt(out)


def kp_for(w_um, l_nm, tox_nm=4.0, mu0=450.0, temp_c=27.0):
    k, _, l_cm = mosfet_constants(l_nm, w_um, tox_nm, mu0, temp_c)
    return k * l_cm / (w_um * 1e-4)          # KP = mu*Cox, A/V^2


def load(netlist):
    parsed = parse_netlist_full(netlist)
    c = Circuit()
    for el in parsed.elements:
        c.add(el)
    return c, parsed


def style(ax):
    ax.grid(True, color="#e6e0d4", linewidth=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


# ---------------------------------------------------------------- 1. AC: common-source amplifier
def figure_ac():
    W, L, CGD = 2.0, 180.0, 1e-12
    net = (f"Vdd 1 0 1.8\nVin 4 0 0.8 AC 1\nRs 4 2 10k\nRd 1 3 2k\n"
           f"M1 3 2 0 0 NMOS W={W} L={L} LAMBDA=0 CGD={CGD}\n.ac dec 20 10 1g\n")
    c, p = load(net)
    f = np.array(p.ac.values())
    ours = c.ac_analysis(list(f))["V(3)"]
    deck = (f"CS amp\n{TIGHT}Vdd 1 0 1.8\nVin 4 0 DC 0.8 AC 1\nRs 4 2 10k\nRd 1 3 2k\nM1 3 2 0 0 NM W={W}u L={L}n\n"
            f".model NM NMOS (LEVEL=1 VTO=0.4 KP={kp_for(W, L):.9g} GAMMA=0.4 PHI=0.6 LAMBDA=0 CGDO={CGD / (W * 1e-6):.9g})\n"
            f".ac dec 20 10 1g")
    t = ngspice(deck, "ac dec 20 10 1g\nwrdata {out} vdb(3) vp(3)")
    f2, db2, ph2 = t[:, 0], t[:, 1], t[:, 3]
    d_db = np.array(ours["db"]) - db2
    d_ph = np.array(ours["phase_deg"]) - ph2

    fig, ax = plt.subplots(3, 1, figsize=(8, 8.2), sharex=True, gridspec_kw={"height_ratios": [3, 3, 1.4]})
    ax[0].semilogx(f, ours["db"], color=ACCENT, lw=2.2, label="AnalogSim")
    ax[0].semilogx(f2, db2, "o", color=SPICE, ms=4.5, mfc="none", label="ngspice 42 (LEVEL 1)")
    ax[1].semilogx(f, ours["phase_deg"], color=ACCENT, lw=2.2)
    ax[1].semilogx(f2, ph2, "o", color=SPICE, ms=4.5, mfc="none")
    ax[2].semilogx(f, d_db, color=ACCENT, lw=1.5, label="gain (dB)")
    ax[2].semilogx(f, d_ph, color=SPICE, lw=1.5, ls="--", label="phase (deg)")
    ax[0].set_ylabel("Gain V(3)/Vin (dB)")
    ax[1].set_ylabel("Phase (deg)")
    ax[2].set_ylabel("AnalogSim - ngspice")
    ax[2].set_xlabel("Frequency (Hz)")
    ax[0].legend(frameon=False)
    ax[2].legend(frameon=False, loc="upper left", ncol=2)
    ax[2].set_ylim(-1e-3, 1e-3)
    ax[0].set_title("Common-source amplifier, small-signal AC: AnalogSim vs ngspice\n"
                    "Rs=10k, Rd=2k, Vg=0.8 V, W/L=2u/180n, Cgd=1 pF (Miller pole), LAMBDA=0", fontsize=10.5)
    for a in ax:
        style(a)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "validation-ac-common-source.png")
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path, float(np.max(np.abs(d_db))), float(np.max(np.abs(d_ph)))


# ---------------------------------------------------------------- 2. DC: CMOS inverter transfer curve
def figure_vtc():
    VDD, LN = 1.8, 180.0
    WN, WP = 1.0, 2.0
    vin = np.round(np.arange(0.0, VDD + 1e-9, 0.02), 6)
    net = (f"Vdd 1 0 {VDD}\nVin 2 0 0\nM1 3 2 0 0 NMOS W={WN} L={LN} LAMBDA=0\n"
           f"M2 3 2 1 1 PMOS W={WP} L={LN} LAMBDA=0\n")
    c, _ = load(net)
    series, _ = c.dc_sweep("Vin", list(vin))
    ours = np.array(series["V(3)"])
    deck = (f"Inverter\n{TIGHT}Vdd 1 0 DC {VDD}\nVin 2 0 DC 0\nM1 3 2 0 0 NM W={WN}u L={LN}n\nM2 3 2 1 1 PM W={WP}u L={LN}n\n"
            f".model NM NMOS (LEVEL=1 VTO=0.4 KP={kp_for(WN, LN):.9g} GAMMA=0.4 PHI=0.6 LAMBDA=0)\n"
            f".model PM PMOS (LEVEL=1 VTO=-0.4 KP={kp_for(WP, LN):.9g} GAMMA=0.4 PHI=0.6 LAMBDA=0)\n"
            f".dc Vin 0 {VDD} 0.02")
    t = ngspice(deck, "dc Vin 0 %s 0.02\nwrdata {out} v(3)" % VDD)
    v2, o2 = t[:, 0], t[:, 1]
    n = min(len(vin), len(v2))
    diff_uv = (ours[:n] - o2[:n]) * 1e6

    fig, ax = plt.subplots(2, 1, figsize=(8, 6.6), sharex=True, gridspec_kw={"height_ratios": [4, 1.3]})
    ax[0].plot(vin, ours, color=ACCENT, lw=2.2, label="AnalogSim")
    ax[0].plot(v2[::2], o2[::2], "o", color=SPICE, ms=4.5, mfc="none", label="ngspice 42 (LEVEL 1)")
    ax[1].plot(vin[:n], diff_uv, color=ACCENT, lw=1.5)
    ax[1].set_ylim(-1, 1)
    ax[0].set_ylabel("Vout (V)")
    ax[1].set_ylabel("AnalogSim - ngspice (uV)")
    ax[1].set_xlabel("Vin (V)")
    ax[0].legend(frameon=False)
    ax[0].set_title("CMOS inverter voltage-transfer curve: AnalogSim vs ngspice\n"
                    "VDD=1.8 V, NMOS 1u/180n, PMOS 2u/180n, |Vth|=0.4 V, LAMBDA=0", fontsize=10.5)
    for a in ax:
        style(a)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "validation-dc-inverter-vtc.png")
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path, float(np.max(np.abs(diff_uv)))


if __name__ == "__main__":
    if shutil.which("ngspice") is None:
        sys.exit("ngspice not found on PATH -- install it first (https://ngspice.sourceforge.io)")
    os.makedirs(OUT_DIR, exist_ok=True)
    p1, ddb, dph = figure_ac()
    print(f"wrote {p1}\n  worst difference: {ddb:.2e} dB, {dph:.2e} deg")
    p2, dmv = figure_vtc()
    print(f"wrote {p2}\n  worst difference: {dmv:.4f} uV")
