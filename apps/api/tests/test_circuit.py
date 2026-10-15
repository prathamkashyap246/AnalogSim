"""
Pytest suite for the circuit solver. Run from apps/api:   python -m pytest -q

Every expected value is independent of the solver: closed-form circuit theory,
or the MOSFET model function called directly.
"""
import math

import numpy as np
import pytest

from app.engines.circuit import Circuit, ConvergenceError
from app.engines.netlist_parser import NetlistError, parse_netlist_full
from app.engines.non_ideal_engine import calculate_non_ideal_current, mosfet_constants


def build(netlist):
    parsed = parse_netlist_full(netlist)
    c = Circuit()
    for el in parsed.elements:
        c.add(el)
    return c, parsed


# ---------------------------------------------------------------- linear DC
def test_resistor_divider():
    c, _ = build("Vin 1 0 9\nR1 1 2 1k\nR2 2 0 1k")
    assert c.solve()["V(2)"] == pytest.approx(4.5, abs=1e-9)


def test_current_source_into_resistor():
    c, _ = build("I1 0 1 1m\nR1 1 0 2k")  # 1 mA pushed into node 1 -> 2 V
    assert c.solve()["V(1)"] == pytest.approx(2.0, abs=1e-9)


def test_capacitor_is_open_at_dc():
    c, _ = build("Vin 1 0 5\nR1 1 2 1k\nC1 2 0 1u\nR2 2 0 1k")
    assert c.solve()["V(2)"] == pytest.approx(2.5, abs=1e-9)


# ------------------------------------------------------------------ MOSFET
VDD_NETLIST = "Vdd 1 0 1.8\nVg 2 0 1.0\nRd 1 3 10k\nM1 3 2 0 0 NMOS W=2 L=180\n"


def test_common_source_operating_point_satisfies_kcl_and_model():
    c, _ = build(VDD_NETLIST)
    r = c.solve()
    m = c.elements[-1]
    # Id from the solver must equal Id from the model at the solved voltages
    vds = r["V(3)"]
    i_model = m.drain_current(vds, 1.0, 0.0, 0.0)
    assert r["Id(M1)"] == pytest.approx(i_model, rel=1e-9)
    # and KCL at the drain: current through Rd equals the drain current
    assert (1.8 - vds) / 10e3 == pytest.approx(r["Id(M1)"], rel=1e-6)


def test_nmos_saturation_current_matches_square_law():
    k, mu, l_cm = mosfet_constants(180.0, 1.0, 4.0, 450.0, 27.0)
    i, _, _, _ = calculate_non_ideal_current(1.0, 1.8, 0.0, 27.0, 0.4, k, mu, l_cm, 0.0, 0.4, 0.6, True, False, False)
    assert i == pytest.approx(0.5 * k * (1.0 - 0.4) ** 2, rel=1e-12)


def test_cmos_inverter_vtc_is_monotonic_and_rail_to_rail():
    net = "Vdd 1 0 1.8\nVin 2 0 0\nM1 3 2 0 0 NMOS W=1 L=180\nM2 3 2 1 1 PMOS W=2 L=180\n"
    c, _ = build(net)
    vin = [round(0.05 * i, 3) for i in range(37)]
    series, _ = c.dc_sweep("Vin", vin)
    vout = series["V(3)"]
    assert vout[0] == pytest.approx(1.8, abs=1e-3)
    assert vout[-1] == pytest.approx(0.0, abs=1e-3)
    assert all(a >= b - 1e-9 for a, b in zip(vout, vout[1:]))


def test_dc_sweep_restores_source_value():
    c, _ = build("Vin 1 0 3\nR1 1 0 1k")
    c.dc_sweep("Vin", [0.0, 1.0, 2.0])
    assert c.solve()["V(1)"] == pytest.approx(3.0)


# ---------------------------------------------------------------------- AC
def test_rc_lowpass_corner_is_minus_3db_and_minus_45_degrees():
    r, cap = 1e3, 1e-7
    fc = 1 / (2 * math.pi * r * cap)
    c, _ = build(f"Vin 1 0 0 AC 1\nR1 1 2 {r}\nC1 2 0 {cap}")
    out = c.ac_analysis([fc])["V(2)"]
    assert out["db"][0] == pytest.approx(-3.0103, abs=1e-3)
    assert out["phase_deg"][0] == pytest.approx(-45.0, abs=1e-3)


def test_rc_lowpass_matches_closed_form_across_frequency():
    r, cap = 2.2e3, 4.7e-9
    freqs = [10.0, 1e3, 3e4, 1e6]
    c, _ = build(f"Vin 1 0 0 AC 1\nR1 1 2 {r}\nC1 2 0 {cap}")
    out = c.ac_analysis(freqs)["V(2)"]
    for f, mag, ph in zip(freqs, out["mag"], out["phase_deg"]):
        h = 1 / (1 + 1j * 2 * math.pi * f * r * cap)
        # rel=1e-7: the solver adds GMIN (1e-12 S) from every node to ground, ~2e-9 effect here
        assert mag == pytest.approx(abs(h), rel=1e-7)
        assert ph == pytest.approx(math.degrees(np.angle(h)), abs=1e-6)


def test_common_source_midband_gain_is_minus_gm_times_rd_parallel_ro():
    c, _ = build("Vdd 1 0 1.8\nVg 2 0 0.8 AC 1\nRd 1 3 10k\nM1 3 2 0 0 NMOS W=2 L=180\n")
    r = c.solve()
    m = c.elements[-1]
    gm, gds = _small_signal(m, r)
    expected = -gm / (gds + 1 / 10e3)
    got = c.ac_analysis([1.0])["V(3)"]
    assert got["mag"][0] == pytest.approx(abs(expected), rel=1e-4)
    assert abs(got["phase_deg"][0]) == pytest.approx(180.0, abs=0.01)


def test_common_source_cgd_gives_miller_pole():
    """With a source resistance, Cgd is multiplied by (1+|A|) (Miller effect).
    Predicted pole: 1 / (2*pi*Rs*Cgd*(1+|A|)); gain there is |A|/sqrt(2)."""
    net = "Vdd 1 0 1.8\nVin 4 0 0.8 AC 1\nRs 4 2 100k\nRd 1 3 10k\nM1 3 2 0 0 NMOS W=2 L=180 {cgd}\n"
    flat, _ = build(net.format(cgd=""))
    a0 = flat.ac_analysis([1.0])["V(3)"]["mag"][0]
    assert flat.ac_analysis([1e8])["V(3)"]["mag"][0] == pytest.approx(a0, rel=1e-6)  # no caps -> no pole

    c, _ = build(net.format(cgd="CGD=1p"))
    fp = 1 / (2 * math.pi * 100e3 * 1e-12 * (1 + a0))
    at_pole = c.ac_analysis([fp])["V(3)"]["mag"][0]
    assert at_pole == pytest.approx(a0 / math.sqrt(2), rel=0.05)


def test_ac_requires_an_ac_source():
    c, _ = build("Vin 1 0 5\nR1 1 0 1k")
    with pytest.raises(ValueError):
        c.ac_analysis([1e3])


def _small_signal(m, op):
    """gm and gds from central differences on the model function (independent of stamp_ac)."""
    vd, vg = op["V(3)"], 0.8
    h = 1e-6
    gm = (m.drain_current(vd, vg + h, 0, 0) - m.drain_current(vd, vg - h, 0, 0)) / (2 * h)
    gds = (m.drain_current(vd + h, vg, 0, 0) - m.drain_current(vd - h, vg, 0, 0)) / (2 * h)
    return gm, gds


# ------------------------------------------------------------------ parser
def test_parser_spice_suffixes():
    c, p = build("Vin 1 0 0 AC 1\nR1 1 2 1k\nC1 2 0 10n\n.ac dec 5 1 1meg")
    assert c.elements[1].resistance == 1000.0
    assert c.elements[2].capacitance == pytest.approx(1e-8)
    assert p.ac.stop == 1e6


def test_ac_dec_sweep_point_count():
    _, p = build("Vin 1 0 0 AC 1\nR1 1 0 1k\n.ac dec 10 1 1e6")
    assert len(p.ac.values()) == 61  # 6 decades * 10 + 1


@pytest.mark.parametrize("bad", [
    "Vin 1 0 5\nR1 1 0 -5",                         # negative resistance
    "Vin 1 0 5\nR1 1 0 1k\nR1 1 0 2k",              # duplicate name
    "Vin 1 0 5\nX1 1 0 1k",                         # unknown element
    "Vin 1 0 5\nR1 1 0 1k\n.ac dec 10 1 1e6",       # .ac without AC source
    "Vin 1 0 0 AC 1\nR1 1 0 1k\n.dc Vin 0 1 0.1\n.ac dec 10 1 1e6",  # both analyses
    "Vin 1 0 5\nM1 1 1 0 0 NMOS FOO=3",             # unknown MOSFET param
    "",                                             # empty
])
def test_parser_rejects_bad_netlists(bad):
    with pytest.raises(NetlistError):
        parse_netlist_full(bad)


def test_non_convergence_is_reported():
    # MOSFET gate and drain floating-ish with no DC path -> should raise, not hang
    c, _ = build("Vin 1 0 1\nM1 2 1 0 0 NMOS\nI1 0 2 1")  # forces 1 A through a tiny device
    with pytest.raises(ConvergenceError):
        c.solve()
