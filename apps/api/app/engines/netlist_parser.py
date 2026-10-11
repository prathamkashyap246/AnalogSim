"""
netlist_parser.py — Parses a raw SPICE-style netlist text block into
element objects for circuit.py's Circuit class.

Supported syntax (deliberately minimal, mirrors real SPICE conventions):

    Vin 1 0 5            -> VoltageSource, node_p=1, node_n=0, 5 V
    Iload 0 2 1e-3       -> CurrentSource, 1 mA flowing 0 -> (source) -> 2
    R1 1 2 1000          -> Resistor, 1000 ohms
    M1 d g s b NMOS W=1 L=180
                         -> MOSFET (NMOS or PMOS); drain, gate, source, bulk
    * this is a comment, ignored
    .dc Vin 0 1.8 0.05   -> sweep source Vin from 0 to 1.8 V in 0.05 V steps
    .op / .end           -> accepted and ignored (.end stops parsing)
    (blank lines are ignored)

MOSFET parameters (all optional, KEY=VALUE, case-insensitive):
    W      gate width in micrometres   (default 1)
    L      gate length in nanometres   (default 180)
    TOX    oxide thickness in nm       (default 4)
    VTH0   zero-bias threshold in V    (default 0.4)
    GAMMA  body-effect coefficient     (default 0.4)
    LAMBDA channel-length modulation   (default 0.05)
Note W is in um and L is in nm (the units used everywhere else in this
project), not metres as in standard SPICE.

Element type is determined by the first character of the name (V, I, R, M).
Node numbers are integers; 0 is ground.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from app.engines.circuit import CurrentSource, Mosfet, Resistor, VoltageSource

Element = Union[Resistor, VoltageSource, CurrentSource, Mosfet]

MAX_SWEEP_POINTS = 2000


class NetlistError(Exception):
    """Raised when a netlist line can't be parsed."""
    pass


@dataclass
class DcSweep:
    """A parsed '.dc <source> <start> <stop> <step>' directive."""
    source: str
    start: float
    stop: float
    step: float

    def values(self) -> List[float]:
        n = int(math.floor((self.stop - self.start) / self.step + 1e-9)) + 1
        # start + i*step (not repeated addition) so rounding error doesn't accumulate
        return [round(self.start + i * self.step, 12) for i in range(n)]


_MOS_PARAMS = {
    "W": "gate_width_um",
    "L": "gate_length_nm",
    "TOX": "tox_nm",
    "VTH0": "vth0",
    "GAMMA": "gamma",
    "LAMBDA": "lambda_param",
}
_MOS_MUST_BE_POSITIVE = {"W", "L", "TOX"}


def _parse_mosfet(parts: List[str], line_num: int, line: str) -> Mosfet:
    if len(parts) < 6:
        raise NetlistError(
            f"Line {line_num}: expected 'name drain gate source bulk NMOS|PMOS [W=..] [L=..]', "
            f"got: '{line}'"
        )

    name = parts[0]
    try:
        d, g, s, b = (int(p) for p in parts[1:5])
    except ValueError:
        raise NetlistError(
            f"Line {line_num}: MOSFET nodes (drain gate source bulk) must be integers, got: '{line}'"
        )

    model = parts[5].upper()
    if model not in ("NMOS", "PMOS"):
        raise NetlistError(
            f"Line {line_num}: MOSFET model must be NMOS or PMOS, got '{parts[5]}'"
        )

    kwargs = {}
    for token in parts[6:]:
        if "=" not in token:
            raise NetlistError(
                f"Line {line_num}: MOSFET parameter must look like KEY=VALUE, got '{token}'"
            )
        key, _, val = token.partition("=")
        key = key.upper()
        if key not in _MOS_PARAMS:
            raise NetlistError(
                f"Line {line_num}: unknown MOSFET parameter '{key}' "
                f"(supported: {', '.join(_MOS_PARAMS)})"
            )
        try:
            num = float(val)
        except ValueError:
            raise NetlistError(f"Line {line_num}: value for {key} must be numeric, got '{val}'")
        if key in _MOS_MUST_BE_POSITIVE and num <= 0:
            raise NetlistError(f"Line {line_num}: {key} must be positive, got {num}")
        kwargs[_MOS_PARAMS[key]] = num

    return Mosfet(
        node_d=d, node_g=g, node_s=s, node_b=b,
        polarity="n" if model == "NMOS" else "p",
        name=name, **kwargs,
    )


def _parse_dc(parts: List[str], line_num: int, line: str) -> DcSweep:
    if len(parts) != 5:
        raise NetlistError(
            f"Line {line_num}: expected '.dc source start stop step', got: '{line}'"
        )
    try:
        start, stop, step = (float(p) for p in parts[2:5])
    except ValueError:
        raise NetlistError(f"Line {line_num}: .dc start, stop and step must be numeric, got: '{line}'")

    if step == 0:
        raise NetlistError(f"Line {line_num}: .dc step must not be zero")
    if (stop - start) * step < 0:
        raise NetlistError(
            f"Line {line_num}: .dc step has the wrong sign to get from {start:g} to {stop:g} "
            f"(use a {'positive' if stop > start else 'negative'} step)"
        )
    n_points = int(math.floor((stop - start) / step + 1e-9)) + 1
    if n_points > MAX_SWEEP_POINTS:
        raise NetlistError(
            f"Line {line_num}: .dc would need {n_points} points; the limit is {MAX_SWEEP_POINTS}. "
            f"Use a larger step."
        )
    return DcSweep(source=parts[1], start=start, stop=stop, step=step)


def parse_netlist(text: str) -> List[Element]:
    """Elements only. Directives such as .dc are accepted but not returned;
    use parse_netlist_with_directives() to get them."""
    return parse_netlist_with_directives(text)[0]


def parse_netlist_with_directives(text: str) -> Tuple[List[Element], Optional[DcSweep]]:
    elements: List[Element] = []
    seen_names = set()
    dc: Optional[DcSweep] = None

    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line or line.startswith("*"):
            continue

        parts = line.split()
        name = parts[0]
        kind = name[0].upper()

        if name.startswith("."):
            directive = name.lower()
            if directive == ".end":
                break
            if directive == ".op":
                continue
            if directive == ".dc":
                if dc is not None:
                    raise NetlistError(f"Line {line_num}: only one .dc directive is supported")
                dc = _parse_dc(parts, line_num, line)
                continue
            raise NetlistError(
                f"Line {line_num}: unsupported directive '{name}' (supported: .dc, .op, .end)"
            )

        if kind not in ("V", "I", "R", "M"):
            raise NetlistError(
                f"Line {line_num}: unrecognized element type '{kind}' "
                f"(name must start with V, I, R or M), got: '{line}'"
            )

        if name.upper() in seen_names:
            raise NetlistError(f"Line {line_num}: duplicate element name '{name}'")
        seen_names.add(name.upper())

        if kind == "M":
            elements.append(_parse_mosfet(parts, line_num, line))
            continue

        if len(parts) != 4:
            raise NetlistError(
                f"Line {line_num}: expected 'name node_p node_n value', "
                f"got: '{line}'"
            )

        _, node_p_str, node_n_str, value_str = parts

        try:
            node_p = int(node_p_str)
            node_n = int(node_n_str)
            value = float(value_str)
        except ValueError:
            raise NetlistError(
                f"Line {line_num}: nodes must be integers and value must "
                f"be numeric, got: '{line}'"
            )

        if kind == "V":
            elements.append(VoltageSource(node_p=node_p, node_n=node_n, voltage=value, name=name))
        elif kind == "I":
            elements.append(CurrentSource(node_p=node_p, node_n=node_n, current=value, name=name))
        else:  # R
            if value <= 0:
                raise NetlistError(f"Line {line_num}: resistance must be positive, got: '{line}'")
            elements.append(Resistor(node_p=node_p, node_n=node_n, resistance=value, name=name))

    if not elements:
        raise NetlistError("Netlist is empty -- no valid element lines found.")

    if dc is not None:
        match = next(
            (e for e in elements
             if isinstance(e, (VoltageSource, CurrentSource)) and e.name.upper() == dc.source.upper()),
            None,
        )
        if match is None:
            raise NetlistError(
                f".dc source '{dc.source}' is not a voltage or current source in this netlist"
            )
        dc.source = match.name  # canonical spelling from the element line

    return elements, dc