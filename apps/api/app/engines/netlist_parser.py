"""
netlist_parser.py — Parses a raw SPICE-style netlist text block into
Resistor/VoltageSource objects for circuit.py's Circuit class.

Supported syntax (deliberately minimal, mirrors real SPICE conventions):

    Vin 1 0 5          -> VoltageSource named "Vin", node_p=1, node_n=0, 5V
    R1 1 2 1000        -> Resistor named "R1", node_p=1, node_n=2, 1000 ohms
    * this is a comment, ignored
    (blank lines are ignored)

Element type is determined by the first character of the name:
    V -> VoltageSource
    R -> Resistor
"""

from typing import List, Union

from app.engines.circuit import Resistor, VoltageSource


class NetlistError(Exception):
    """Raised when a netlist line can't be parsed."""
    pass


def parse_netlist(text: str) -> List[Union[Resistor, VoltageSource]]:
    elements: List[Union[Resistor, VoltageSource]] = []

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("*"):
            continue

        parts = line.split()
        if len(parts) != 4:
            raise NetlistError(
                f"Line {line_num}: expected 'name node_p node_n value', "
                f"got: '{line}'"
            )

        name, node_p_str, node_n_str, value_str = parts

        try:
            node_p = int(node_p_str)
            node_n = int(node_n_str)
            value = float(value_str)
        except ValueError:
            raise NetlistError(
                f"Line {line_num}: nodes must be integers and value must "
                f"be numeric, got: '{line}'"
            )

        kind = name[0].upper()

        if kind == "V":
            elements.append(
                VoltageSource(node_p=node_p, node_n=node_n, voltage=value, name=name)
            )
        elif kind == "R":
            elements.append(
                Resistor(node_p=node_p, node_n=node_n, resistance=value, name=name)
            )
        else:
            raise NetlistError(
                f"Line {line_num}: unrecognized element type '{kind}' "
                f"(name must start with V or R), got: '{line}'"
            )

    if not elements:
        raise NetlistError("Netlist is empty -- no valid element lines found.")

    return elements