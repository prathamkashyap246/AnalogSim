"""
validate_nonlinear.py — Checks for the Newton-Raphson MOSFET solver.

Run:  python validate_nonlinear.py      (from apps/api)

Every expected value comes from something INDEPENDENT of the solver:
a closed-form result, or a 1-D bisection that calls the MOSFET model
function directly. Nothing here reuses Circuit.solve() to produce its
own reference.
"""

from app.engines.circuit import Circuit, ConvergenceError, CurrentSource, Mosfet, Resistor, VoltageSource
from app.engines.netlist_parser import NetlistError, parse_netlist, parse_netlist_with_directives
from app.engines.non_ideal_engine import calculate_non_ideal_current, mosfet_constants

failures = 0


def parse_dc(netlist):
    """Parse a netlist that must contain a .dc line and return the sweep."""
    _, dc = parse_netlist_with_directives(netlist)
    assert dc is not None, "netlist has no .dc directive"
    return dc


def check(label, actual, expected, tol=1e-6):
    global failures
    ok = abs(actual - expected) <= tol
    failures += (not ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: got {actual:.9f}, expected {expected:.9f}")


def solve(netlist):
    c = Circuit()
    for el in parse_netlist(netlist):
        c.add(el)
    return c.solve(), c


# Same defaults as a netlist MOSFET with no parameters.
K, MU, L_CM = mosfet_constants(180.0, 1.0, 4.0, 450.0, 27.0)


def model_id(vgs, vds, vsb=0.0):
    return calculate_non_ideal_current(
        vgs, vds, vsb, 27.0, 0.4, K, MU, L_CM, 0.05, 0.4, 0.6, True, True, False
    )[0]


def bisect(f, lo, hi, n=200):
    """root of f on [lo, hi]; f(lo) and f(hi) must differ in sign"""
    flo = f(lo)
    for _ in range(n):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


# --- 1. current source sign convention (SPICE) ------------------------------
r, _ = solve("I1 1 0 1e-3\nR1 1 0 1000")
check("I1 1 0 into R: V(1) = -1 V (SPICE convention)", r["V(1)"], -1.0, 1e-9)
r, _ = solve("I1 0 1 1e-3\nR1 1 0 1000")
check("I1 0 1 into R: V(1) = +1 V", r["V(1)"], 1.0, 1e-9)

# --- 2. diode-connected NMOS, closed form -----------------------------------
# Saturated, Vds = Vgs  =>  Vds - Vds_sat = Vth, so
#   I = 0.5*k*(V-Vth)^2 * (1 + lambda*Vth)  =>  V = Vth + sqrt(2I / (k(1+lambda*Vth)))
# The solver adds GMIN = 1e-12 S from every node to ground (so a cut-off device
# never leaves a node floating). That leaks ~V*GMIN of current, shifting V by up
# to ~ V*GMIN/gm ~ 7e-9 V at 1 uA -- hence the 5e-8 tolerance, not 1e-9.
for i_src in (1e-6, 1e-5, 1e-4, 2e-4):
    r, c = solve(f"I1 0 1 {i_src}\nM1 1 1 0 0 NMOS")
    expected = 0.4 + (2 * i_src / (K * (1 + 0.05 * 0.4))) ** 0.5
    check(f"diode-connected NMOS, I={i_src:.0e} A: V(1)", r["V(1)"], expected, 5e-8)

# --- 3. common-source amp vs bisection on the model -------------------------
def cs_expected(vdd, vg, rd):
    return bisect(lambda vd: (vdd - vd) / rd - model_id(vg, vd), 0.0, vdd)

for vg, rd, tag in ((0.9, 2000, "saturation"), (1.8, 10000, "deep triode"),
                    (0.6, 5000, "near threshold"), (1.2, 3000, "mid")):
    r, c = solve(f"Vdd 1 0 1.8\nVg 2 0 {vg}\nR1 1 3 {rd}\nM1 3 2 0 0 NMOS")
    check(f"CS amp Vg={vg} RD={rd} ({tag}): V(3)", r["V(3)"], cs_expected(1.8, vg, rd), 1e-7)

r, c = solve("Vdd 1 0 1.8\nVg 2 0 0.2\nR1 1 3 2000\nM1 3 2 0 0 NMOS")
check("CS amp, device cut off: V(3) = Vdd", r["V(3)"], 1.8, 1e-6)

# --- 4. body effect (source above bulk) -------------------------------------
# Source follower: Vs = R*Id(vgs = Vg - Vs, vds = Vdd - Vs, vsb = Vs)
vdd, vg, rs = 1.8, 1.5, 1000.0
expected_vs = bisect(lambda vs: vs / rs - model_id(vg - vs, vdd - vs, vs), 0.0, vg)
r, c = solve(f"Vdd 1 0 {vdd}\nVg 2 0 {vg}\nM1 1 2 3 0 NMOS\nR1 3 0 {rs}")
check("source follower with body effect: V(3)", r["V(3)"], expected_vs, 1e-7)

# --- 5. source/drain role swap (drain pulled below source) ------------------
# Node 3 (labelled "drain") sits below node 1 (labelled "source"), so the roles
# swap: node 1 acts as drain, node 3 as source. Current flows 1 -> device -> 3 -> R -> gnd,
# so  V(3)/R = Id_model(vgs = Vg-V3, vds = 0.5-V3, vsb = V3)
r, c = solve("Vs 1 0 0.5\nVg 2 0 1.2\nR1 3 0 1000\nM1 3 2 1 0 NMOS")
expected_vd = bisect(lambda vd: vd / 1000.0 - model_id(1.2 - vd, 0.5 - vd, vd), 0.0, 0.5)
check("reversed-polarity conduction: V(3)", r["V(3)"], expected_vd, 1e-7)

# --- 6. CMOS inverter -------------------------------------------------------
def inverter(vin):
    return solve(f"Vdd 1 0 1.8\nVin 2 0 {vin}\nM1 3 2 0 0 NMOS\nM2 3 2 1 1 PMOS")

r, _ = inverter(0.0);  check("inverter Vin=0:   Vout = Vdd", r["V(3)"], 1.8, 1e-6)
r, _ = inverter(1.8);  check("inverter Vin=Vdd: Vout = 0",   r["V(3)"], 0.0, 1e-6)
r, _ = inverter(0.9);  check("inverter Vin=Vdd/2 (symmetric pair): Vout = Vdd/2", r["V(3)"], 0.9, 1e-6)
check("inverter Vin=Vdd/2: KCL at output, Id(M1)+Id(M2) = 0", r["Id(M1)"] + r["Id(M2)"], 0.0, 1e-12)

prev, mono, worst_iters = 1.9, True, 0
for step in range(0, 37):
    r, c = inverter(step * 0.05)
    mono &= r["V(3)"] <= prev + 1e-9
    prev = r["V(3)"]
    worst_iters = max(worst_iters, c.last_iterations)
    # KCL at the output node must hold for every point
    assert abs(r["Id(M1)"] + r["Id(M2)"]) < 1e-9, f"KCL violated at Vin={step*0.05}"
print(f"[{'PASS' if mono else 'FAIL'}] inverter VTC: 37 points all converge, Vout monotonically non-increasing "
      f"(worst case {worst_iters} Newton iterations)")
failures += (not mono)

# --- 7. parser guard rails ---------------------------------------------------
for label, text in (("duplicate name", "R1 1 0 100\nR1 1 2 100"),
                    ("zero resistance", "V1 1 0 1\nR1 1 0 0"),
                    ("bad MOS model", "M1 1 2 0 0 BJT"),
                    ("unknown MOS param", "M1 1 2 0 0 NMOS FOO=3")):
    try:
        parse_netlist(text)
        ok = False
    except NetlistError:
        ok = True
    failures += (not ok)
    print(f"[{'PASS' if ok else 'FAIL'}] parser rejects {label}")

# --- 8. .dc sweep -------------------------------------------------------------
def sweep(netlist):
    elements, dc = parse_netlist_with_directives(netlist)
    assert dc is not None, "netlist has no .dc directive"
    c = Circuit()
    for el in elements:
        c.add(el)
    series, iters = c.dc_sweep(dc.source, dc.values())
    return dc, series, iters, c


def flag(label, ok):
    global failures
    failures += (not ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")


# 8a. parser: point counts, direction, canonical source name
dc = parse_dc("Vin 1 0 0\nR1 1 0 1\n.dc VIN 0 1.8 0.05")
flag("parse .dc: 37 points from 0 to 1.8", len(dc.values()) == 37 and dc.values()[0] == 0.0 and dc.values()[-1] == 1.8)
flag("parse .dc: source name taken from the element line (VIN -> Vin)", dc.source == "Vin")
dc = parse_dc("Vin 1 0 0\nR1 1 0 1\n.dc Vin 1 0 -0.25")
flag("parse .dc: downward sweep 1 -> 0 gives 5 points", dc.values() == [1.0, 0.75, 0.5, 0.25, 0.0])
for label, text in (("unknown source", ".dc Vx 0 1 0.1"), ("resistor as source", ".dc R1 0 1 0.1"),
                    ("zero step", ".dc Vin 0 1 0"), ("wrong-sign step", ".dc Vin 0 1 -0.1"),
                    ("too many points", ".dc Vin 0 1 0.0001"), ("missing field", ".dc Vin 0 1"),
                    ("second .dc", ".dc Vin 0 1 0.1\n.dc Vin 0 2 0.1"), ("unsupported directive", ".tran 1n 1u")):
    try:
        parse_netlist_with_directives("Vin 1 0 0\nR1 1 0 1\n" + text)
        ok = False
    except NetlistError:
        ok = True
    flag(f"parser rejects .dc case: {label}", ok)
flag("parse_netlist() still returns plain element list when .dc present",
     len(parse_netlist("Vin 1 0 0\nR1 1 0 1\n.dc Vin 0 1 0.1\n.end")) == 2)

# 8b. linear divider sweep: V(2) = (2/3) * Vin at every point
dc, ser, it, c = sweep("Vin 1 0 0\nR1 1 2 1000\nR2 2 0 2000\n.dc Vin 0 10 1")
err = max(abs(v2 - (2 / 3) * x) for v2, x in zip(ser["V(2)"], dc.values()))
check("linear divider sweep, worst error over 11 points", err, 0.0, 1e-9)

# 8c. source value restored after sweep
elements, dcs = parse_netlist_with_directives("Vin 1 0 3.3\nR1 1 0 1000\n.dc Vin 0 1 0.5")
assert dcs is not None
c = Circuit()
for el in elements:
    c.add(el)
c.dc_sweep(dcs.source, dcs.values())
check("source value restored after sweep (Vin was 3.3)", c.solve()["V(1)"], 3.3, 1e-12)

# 8d. current-source sweep into a resistor: V = I*R
dc, ser, it, c = sweep("I1 0 1 0\nR1 1 0 2000\n.dc I1 0 1e-3 2.5e-4")
err = max(abs(v - i * 2000) for v, i in zip(ser["V(1)"], dc.values()))
check("current-source sweep into 2k resistor, worst error", err, 0.0, 1e-9)

# 8e. CMOS inverter VTC
INV = "Vdd 1 0 1.8\nVin 2 0 0\nM1 3 2 0 0 NMOS\nM2 3 2 1 1 PMOS\n.dc Vin 0 1.8 0.05"
dc, ser, it, c = sweep(INV)
vin, vout = dc.values(), ser["V(3)"]
check("VTC endpoint Vin=0 -> Vout", vout[0], 1.8, 1e-6)
check("VTC endpoint Vin=Vdd -> Vout", vout[-1], 0.0, 1e-6)
check("VTC midpoint Vin=0.9 -> Vout (symmetric pair)", vout[18], 0.9, 1e-6)
flag("VTC monotonically non-increasing across 37 points",
     all(b <= a + 1e-9 for a, b in zip(vout, vout[1:])))
# the pair is mobility- and Vth-matched, so Vout(Vin) + Vout(Vdd - Vin) = Vdd
sym = max(abs(vout[i] + vout[36 - i] - 1.8) for i in range(37))
check("VTC point-symmetry Vout(Vin)+Vout(Vdd-Vin)=Vdd, worst error", sym, 0.0, 1e-6)
kcl = max(abs(a + b) for a, b in zip(ser["Id(M1)"], ser["Id(M2)"]))
check("VTC KCL at output, worst |Id(M1)+Id(M2)| over sweep", kcl, 0.0, 1e-9)

# 8f. warm-started sweep must equal independent cold solves, point by point
worst = 0.0
for x, warm in zip(vin, vout):
    cold = solve(INV.replace("Vin 2 0 0", f"Vin 2 0 {x}").split("\n.dc")[0])[0]["V(3)"]
    worst = max(worst, abs(cold - warm))
check("warm-started sweep vs cold solves, worst difference", worst, 0.0, 1e-7)

cold_iters = [solve(INV.replace("Vin 2 0 0", f"Vin 2 0 {x}").split("\n.dc")[0])[1].last_iterations for x in vin]
flag(f"warm start never slower overall (warm total {sum(it)} vs cold total {sum(cold_iters)} iterations)",
     sum(it) <= sum(cold_iters))

# 8g. common-source amp sweep against bisection reference at every point
dc, ser, it, c = sweep("Vdd 1 0 1.8\nVg 2 0 0\nR1 1 3 5000\nM1 3 2 0 0 NMOS\n.dc Vg 0 1.8 0.1")
err = max(abs(v3 - cs_expected(1.8, vg, 5000)) for v3, vg in zip(ser["V(3)"], dc.values()))
check("CS amp Vg sweep vs bisection reference, worst error over 19 points", err, 0.0, 1e-7)

# 8h. convergence failure names the sweep point
elements, dcs = parse_netlist_with_directives(INV)
assert dcs is not None
c = Circuit()
for el in elements:
    c.add(el)
c.MAX_ITER = 1
try:
    c.dc_sweep(dcs.source, dcs.values())
    flag("non-convergence raises ConvergenceError naming the sweep value", False)
except ConvergenceError as e:
    flag(f"non-convergence raises ConvergenceError naming the sweep value ('{e}')", "Vin = " in str(e))

print("\nAll checks passed." if failures == 0 else f"\n{failures} CHECK(S) FAILED.")
raise SystemExit(1 if failures else 0)