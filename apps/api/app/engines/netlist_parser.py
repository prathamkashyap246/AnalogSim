"""
netlist_parser.py — Parses a raw SPICE-style netlist text block into
element objects for circuit.py's Circuit class.

Supported syntax (deliberately minimal, mirrors real SPICE conventions):

    Vin 1 0 5            -> VoltageSource, node_p=1, node_n=0, 5 V
    Iload 0 2 1e-3       -> CurrentSource, 1 mA flowing 0 -> (source) -> 2
    R1 1 2 1000          -> Resistor, 1000 ohms
    C1 2 0 1n            -> Capacitor, 1 nF (open circuit at DC)
    Vin 1 0 0.9 AC 1     -> source with DC value 0.9 V and AC magnitude 1
                            (also "Vin 1 0 DC 0.9 AC 1"; V and I sources)
    M1 d g s b NMOS W=1 L=180
                         -> MOSFET (NMOS or PMOS); drain, gate, source, bulk
    * this is a comment, ignored
    .dc Vin 0 1.8 0.05   -> sweep source Vin from 0 to 1.8 V in 0.05 V steps
    .ac dec 10 1 1meg    -> small-signal frequency sweep: 10 points per decade
                            from 1 Hz to 1 MHz ("lin N start stop" also works)
    .op / .end           -> accepted and ignored (.end stops parsing)
    (blank lines are ignored)

MOSFET parameters (all optional, KEY=VALUE, case-insensitive):
    W      gate width in micrometres   (default 1)
    L      gate length in nanometres   (default 180)
    TOX    oxide thickness in nm       (default 4)
    VTH0   zero-bias threshold in V    (default 0.4)
    GAMMA  body-effect coefficient     (default 0.4)
    LAMBDA channel-length modulation   (default 0.05)
    CGS    gate-source capacitance, F  (default 0; AC analysis only)
    CGD    gate-drain capacitance, F   (default 0; AC analysis only)
Note W is in um and L is in nm (the units used everywhere else in this
project), not metres as in standard SPICE.

Numbers accept SPICE suffixes: f p n u m k meg g t (so 1k = 1000, 10n = 1e-8,
1meg = 1e6; "m" is milli, as in SPICE). Plain floats like 1e-3 work too.
Element type is determined by the first character of the name (V, I, R, C, M).
Node numbers are integers; 0 is ground.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from app.engines.circuit import Capacitor, CurrentSource, Mosfet, Resistor, VoltageSource

Element = Union[Resistor, Capacitor, VoltageSource, CurrentSource, Mosfet]

MAX_SWEEP_POINTS = 2000

_SUFFIXES = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3,
             "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}


def _num(token: str) -> float:
    """float() that also understands SPICE suffixes (1k, 10n, 1meg, ...)."""
    t = token.strip().lower()
    try:
        return float(t)
    except ValueError:
        pass
    for suffix in ("meg", "t", "g", "k", "m", "u", "n", "p", "f"):
        if t.endswith(suffix):
            return float(t[: -len(suffix)]) * _SUFFIXES[suffix]  # ValueError propagates
    raise ValueError(token)


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


@dataclass
class AcSweep:
    """A parsed '.ac dec|lin <points> <start> <stop>' directive."""
    kind: str      # "dec" (points per decade) or "lin" (total points)
    points: int
    start: float
    stop: float

    def values(self) -> List[float]:
        if self.kind == "lin":
            if self.points == 1:
                return [self.start]
            step = (self.stop - self.start) / (self.points - 1)
            return [self.start + i * step for i in range(self.points)]
        n = int(math.floor(self.points * math.log10(self.stop / self.start) + 1e-9)) + 1
        return [self.start * 10 ** (i / self.points) for i in range(n)]


@dataclass
class ParsedNetlist:
    elements: List[Element]
    dc: Optional[DcSweep] = None
    ac: Optional[AcSweep] = None


_MOS_PARAMS = {
    "W": "gate_width_um",
    "L": "gate_length_nm",
    "TOX": "tox_nm",
    "VTH0": "vth0",
    "GAMMA": "gamma",
    "LAMBDA": "lambda_param",
    "CGS": "cgs",
    "CGD": "cgd",
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
            num = _num(val)
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


def _parse_source_tail(tail: List[str]):
    """Tokens after the nodes on a V/I line: '5', 'DC 5', 'AC 1', '0.9 AC 1', 'DC 0.9 AC 1'."""
    dc, ac, i = 0.0, 0.0, 0
    while i < len(tail):
        t = tail[i].upper()
        if t == "DC":
            dc, i = _num(tail[i + 1]), i + 2
        elif t == "AC":
            ac, i = _num(tail[i + 1]), i + 2
        elif i == 0:
            dc, i = _num(tail[0]), 1
        else:
            raise ValueError(tail[i])
    return dc, ac


def _parse_dc(parts: List[str], line_num: int, line: str) -> DcSweep:
    if len(parts) != 5:
        raise NetlistError(
            f"Line {line_num}: expected '.dc source start stop step', got: '{line}'"
        )
    try:
        start, stop, step = (_num(p) for p in parts[2:5])
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


def _parse_ac(parts: List[str], line_num: int, line: str) -> AcSweep:
    if len(parts) != 5 or parts[1].lower() not in ("dec", "lin"):
        raise NetlistError(
            f"Line {line_num}: expected '.ac dec|lin points start stop', got: '{line}'"
        )
    kind = parts[1].lower()
    try:
        points = int(parts[2])
        start, stop = _num(parts[3]), _num(parts[4])
    except ValueError:
        raise NetlistError(f"Line {line_num}: .ac points must be an integer and start/stop numeric, got: '{line}'")
    if points < 1 or start <= 0 or stop < start:
        raise NetlistError(
            f"Line {line_num}: .ac needs points >= 1, start > 0 and stop >= start, got: '{line}'"
        )
    n_points = AcSweep(kind, points, start, stop).values().__len__()
    if n_points > MAX_SWEEP_POINTS:
        raise NetlistError(
            f"Line {line_num}: .ac would need {n_points} points; the limit is {MAX_SWEEP_POINTS}."
        )
    return AcSweep(kind=kind, points=points, start=start, stop=stop)


def parse_netlist(text: str) -> List[Element]:
    """Elements only. Directives such as .dc are accepted but not returned;
    use parse_netlist_with_directives() to get them."""
    return parse_netlist_with_directives(text)[0]


def parse_netlist_with_directives(text: str) -> Tuple[List[Element], Optional[DcSweep]]:
    """Elements and the .dc sweep (if any). Use parse_netlist_full() for .ac too."""
    parsed = parse_netlist_full(text)
    return parsed.elements, parsed.dc


def parse_netlist_full(text: str) -> ParsedNetlist:
    elements: List[Element] = []
    seen_names = set()
    dc: Optional[DcSweep] = None
    ac: Optional[AcSweep] = None

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
            if directive == ".ac":
                if ac is not None:
                    raise NetlistError(f"Line {line_num}: only one .ac directive is supported")
                ac = _parse_ac(parts, line_num, line)
                continue
            raise NetlistError(
                f"Line {line_num}: unsupported directive '{name}' (supported: .dc, .ac, .op, .end)"
            )

        if kind not in ("V", "I", "R", "C", "M"):
            raise NetlistError(
                f"Line {line_num}: unrecognized element type '{kind}' "
                f"(name must start with V, I, R, C or M), got: '{line}'"
            )

        if name.upper() in seen_names:
            raise NetlistError(f"Line {line_num}: duplicate element name '{name}'")
        seen_names.add(name.upper())

        if kind == "M":
            elements.append(_parse_mosfet(parts, line_num, line))
            continue

        if len(parts) < 4 or (kind in ("R", "C") and len(parts) != 4):
            raise NetlistError(
                f"Line {line_num}: expected 'name node_p node_n value', "
                f"got: '{line}'"
            )

        try:
            node_p = int(parts[1])
            node_n = int(parts[2])
            if kind in ("V", "I"):
                value, ac_mag = _parse_source_tail(parts[3:])
            else:
                value, ac_mag = _num(parts[3]), 0.0
        except (ValueError, IndexError):
            raise NetlistError(
                f"Line {line_num}: nodes must be integers and value must "
                f"be numeric, got: '{line}'"
            )

        if kind == "V":
            elements.append(VoltageSource(node_p=node_p, node_n=node_n, voltage=value, name=name, ac_mag=ac_mag))
        elif kind == "I":
            elements.append(CurrentSource(node_p=node_p, node_n=node_n, current=value, name=name, ac_mag=ac_mag))
        elif kind == "C":
            if value <= 0:
                raise NetlistError(f"Line {line_num}: capacitance must be positive, got: '{line}'")
            elements.append(Capacitor(node_p=node_p, node_n=node_n, capacitance=value, name=name))
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

    if ac is not None:
        if dc is not None:
            raise NetlistError("Use either .dc or .ac in one netlist, not both")
        if not any(isinstance(e, (VoltageSource, CurrentSource)) and e.ac_mag for e in elements):
            raise NetlistError(".ac needs a source with an AC magnitude, e.g. 'Vin 1 0 0 AC 1'")

    return ParsedNetlist(elements=elements, dc=dc, ac=ac)