from typing import Any, Dict
import numpy as np


def calculate_ideal_current(vgs, vds, vth, k_n):
    v_ov = vgs - vth

    if v_ov <= 0:
        return 0.0

    if vds < v_ov:
        return k_n * ((v_ov * vds) - 0.5 * (vds ** 2))
    else:
        return 0.5 * k_n * (v_ov ** 2)


def run_ideal_engine(
    gate_length_nm: float = 180.0,
    gate_width_um: float = 1.0,
    tox_nm: float = 4.0,
    mu_0: float = 450.0,
    vth0: float = 0.4,
    sweep_param: str = "vds",
    sweep_start: float = 0.0,
    sweep_end: float = 1.8,
    steps: int = 50,
    fixed_vgs: float = 1.8,
    fixed_vds: float = 1.2,
) -> Dict[str, Any]:
    eps_ox = 3.9 * 8.854e-14
    tox_cm = tox_nm * 1e-7
    c_ox = eps_ox / tox_cm

    w_cm = gate_width_um * 1e-4
    l_cm = gate_length_nm * 1e-7
    k_n = mu_0 * c_ox * (w_cm / l_cm)

    sweep_vec = np.linspace(sweep_start, sweep_end, steps + 1)

    vds_list, vgs_list, id_list, vth_list = [], [], [], []

    for val in sweep_vec:
        vgs = val if sweep_param == "vgs" else fixed_vgs
        vds = val if sweep_param == "vds" else fixed_vds

        id_val = calculate_ideal_current(vgs, vds, vth0, k_n)

        vds_list.append(float(vds))
        vgs_list.append(float(vgs))
        id_list.append(float(id_val))
        vth_list.append(float(vth0))

    return {
        "vds": vds_list,
        "vgs": vgs_list,
        "id": id_list,
        "vth": vth_list,
        "sweep_param": sweep_param,
        "description": "Ideal (first-order) square-law MOSFET model, no second-order effects.",
    }