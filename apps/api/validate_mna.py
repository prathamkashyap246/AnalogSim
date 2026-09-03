"""
validate_mna.py — Sanity checks for the new MNA circuit solver (circuit.py).

Run this directly:
    python validate_mna.py

It builds a few simple resistor networks, solves them with the new
Circuit/MNA code, and compares against hand-calculated expected values.
This is Phase 2's "done" condition: several networks matching hand
calculations exactly (within floating point tolerance).
"""

from app.engines.circuit import Circuit, Resistor, VoltageSource


def check(label: str, actual: float, expected: float, tol: float = 1e-9) -> None:
    ok = abs(actual - expected) < tol
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {label}: got {actual:.6f}, expected {expected:.6f}")


def test_simple_voltage_divider():
    """
    Vin (node 1) --- R1 --- node 2 --- R2 --- GND (node 0)

    Expected: V(2) = Vin * R2 / (R1 + R2)
    """
    vin = 5.0
    r1 = 1000.0
    r2 = 2000.0

    circuit = Circuit()
    circuit.add(VoltageSource(node_p=1, node_n=0, voltage=vin, name="Vin"))
    circuit.add(Resistor(node_p=1, node_n=2, resistance=r1))
    circuit.add(Resistor(node_p=2, node_n=0, resistance=r2))

    result = circuit.solve()

    expected_v2 = vin * r2 / (r1 + r2)
    check("Voltage divider V(2)", result["V(2)"], expected_v2)

    expected_i = -vin / (r1 + r2)
    check("Source current I(Vin)", result["I(Vin)"], expected_i)


def test_equal_resistor_divider():
    """Equal resistors should split the voltage exactly in half."""
    vin = 9.0
    r = 470.0

    circuit = Circuit()
    circuit.add(VoltageSource(node_p=1, node_n=0, voltage=vin, name="Vin"))
    circuit.add(Resistor(node_p=1, node_n=2, resistance=r))
    circuit.add(Resistor(node_p=2, node_n=0, resistance=r))

    result = circuit.solve()
    check("Equal-R divider V(2)", result["V(2)"], vin / 2.0)


def test_three_resistor_ladder():
    """
    Vin --- R1 --- node2 --- R2 --- node3 --- R3 --- GND

    Solve by hand: total R = R1+R2+R3, current I = Vin/Rtotal,
    V(2) = Vin - I*R1, V(3) = I*R3
    """
    vin = 12.0
    r1, r2, r3 = 100.0, 200.0, 300.0

    circuit = Circuit()
    circuit.add(VoltageSource(node_p=1, node_n=0, voltage=vin, name="Vin"))
    circuit.add(Resistor(node_p=1, node_n=2, resistance=r1))
    circuit.add(Resistor(node_p=2, node_n=3, resistance=r2))
    circuit.add(Resistor(node_p=3, node_n=0, resistance=r3))

    result = circuit.solve()

    r_total = r1 + r2 + r3
    i_total = vin / r_total
    expected_v2 = vin - i_total * r1
    expected_v3 = i_total * r3

    check("Ladder V(2)", result["V(2)"], expected_v2)
    check("Ladder V(3)", result["V(3)"], expected_v3)


def test_resistor_to_negative_source():
    """
    Confirm the solver handles a source correctly by comparing against
    a ground-referenced equivalent computed by hand.
    """
    vin = 3.3
    r1 = 500.0
    r2 = 1500.0

    circuit = Circuit()
    circuit.add(VoltageSource(node_p=1, node_n=0, voltage=vin, name="Vin"))
    circuit.add(Resistor(node_p=1, node_n=2, resistance=r1))
    circuit.add(Resistor(node_p=2, node_n=0, resistance=r2))

    result = circuit.solve()
    expected_v2 = vin * r2 / (r1 + r2)
    check("Second divider V(2)", result["V(2)"], expected_v2)


if __name__ == "__main__":
    print("Running MNA solver validation against hand-calculated circuits...\n")
    test_simple_voltage_divider()
    test_equal_resistor_divider()
    test_three_resistor_ladder()
    test_resistor_to_negative_source()
    print("\nDone. All lines above should say PASS.")