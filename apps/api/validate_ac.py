"""
validate_ac.py -- Cross-checks small-signal AC analysis against ngspice.

Run:  python validate_ac.py      (from apps/api; needs `ngspice` on PATH)

Two circuits, each run through both simulators over the same frequencies:
  1. RC low-pass                     (linear: validates the complex MNA solve)
  2. Common-source amp, Rs + Cgd     (validates the MOSFET small-signal model:
                                      gm from the DC operating point + Miller pole)
For (2) LAMBDA=0 on both sides, because ngspice LEVEL1 applies (1+lambda*Vds)
everywhere while this project applies CLM only in saturation (documented
design choice), which would shift gds slightly and cloud a gm/Cgd check.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

from app.engines.circuit import Circuit
from app.engines.netlist_parser import parse_netlist_full
from app.engines.non_ideal_engine import mosfet_constants

failures = 0
FREQS = "dec 10 1 1e8"


def check(label, actual, tol):
    global failures
    ok = actual <= tol
    failures += (not ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: worst difference {actual:.6f}, tolerance {tol}")


def run_ours(netlist, node):
    parsed = parse_netlist_full(netlist)
    c = Circuit()
    for el in parsed.elements:
        c.add(el)
    f = parsed.ac.values()
    out = c.ac_analysis(f)[f"V({node})"]
    return np.array(f), np.array(out["db"]), np.array(out["phase_deg"])


def run_ngspice(spice_deck, node):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.txt")
        deck = f"""{spice_deck}
.control
set units=degrees
ac {FREQS}
wrdata {out} vdb({node}) vp({node})
.endc
.end
"""
        path = os.path.join(tmp, "deck.cir")
        open(path, "w").write(deck)
        subprocess.run(["ngspice", "-b", path], check=True, capture_output=True, text=True)
        data = np.loadtxt(out)
    return data[:, 0], data[:, 1], data[:, 3]


def compare(label, netlist, spice_deck, node, db_tol=1e-3, deg_tol=0.01):
    f1, db1, ph1 = run_ours(netlist, node)
    f2, db2, ph2 = run_ngspice(spice_deck, node)
    assert len(f1) == len(f2) and np.allclose(f1, f2, rtol=1e-6), "frequency grids differ"
    check(f"{label}: magnitude (dB)", float(np.max(np.abs(db1 - db2))), db_tol)
    check(f"{label}: phase (deg)", float(np.max(np.abs(ph1 - ph2))), deg_tol)


if shutil.which("ngspice") is None:
    sys.exit("ngspice not found on PATH -- install it first (https://ngspice.sourceforge.io)")

# ---- 1. RC low-pass --------------------------------------------------------
compare(
    "RC low-pass (1k, 100nF)",
    "Vin 1 0 0 AC 1\nR1 1 2 1k\nC1 2 0 100n\n.ac dec 10 1 1e8\n",
    "RC\nVin 1 0 DC 0 AC 1\nR1 1 2 1k\nC1 2 0 100n",
    node=2,
)

# ---- 2. Common-source amp with source resistance and Cgd -------------------
W_UM, L_NM, CGD = 2.0, 180.0, 1e-12
k, _, l_cm = mosfet_constants(L_NM, W_UM, 4.0, 450.0, 27.0)
kp = k * l_cm / (W_UM * 1e-4)            # KP = mu*Cox in A/V^2
compare(
    "Common-source amp, Rs=100k, Cgd=1pF",
    f"Vdd 1 0 1.8\nVin 4 0 0.8 AC 1\nRs 4 2 100k\nRd 1 3 10k\n"
    f"M1 3 2 0 0 NMOS W={W_UM} L={L_NM} LAMBDA=0 CGD={CGD}\n.ac dec 10 1 1e8\n",
    f"CS amp\nVdd 1 0 1.8\nVin 4 0 DC 0.8 AC 1\nRs 4 2 100k\nRd 1 3 10k\n"
    f"M1 3 2 0 0 NM W={W_UM}u L={L_NM}n\n"
    f".model NM NMOS (LEVEL=1 VTO=0.4 KP={kp:.9g} GAMMA=0.4 PHI=0.6 LAMBDA=0 CGDO={CGD / (W_UM * 1e-6):.9g})",
    node=3,
)

print()
print("All checks passed." if failures == 0 else f"{failures} check(s) FAILED.")
sys.exit(1 if failures else 0)
