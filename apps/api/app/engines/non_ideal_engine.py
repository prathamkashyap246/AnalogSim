from typing import Any, Dict
import numpy as np


def calculate_non_ideal_current(vgs, vds, vsb, current_temp, vth0, k_val, mu_temp, l_cm, lambda_param, gamma, phi2f, enable_body_effect, enable_clm, enable_velocity_saturation):
    if enable_body_effect and vsb > 0:
        vth = vth0 + gamma * (np.sqrt(max(0.01, phi2f + vsb)) - np.sqrt(phi2f))
    else:
        vth = vth0

    v_ov = vgs - vth

    if v_ov <= 0:
        return 0.0, 0.0, 0.0, vth

    vds_sat = v_ov
    if enable_velocity_saturation:
        v_sat = 1e7
        e_sat = (2 * v_sat) / mu_temp
        l_sat = e_sat * l_cm
        vds_sat = (v_ov * l_sat) / (v_ov + l_sat)

    if vds < vds_sat:
        id_val = k_val * ((v_ov * vds) - 0.5 * (vds ** 2))
    else:
        id_val = 0.5 * k_val * (v_ov ** 2)

    if enable_clm and vds >= vds_sat:
        id_val *= (1 + lambda_param * (vds - vds_sat))

    gm = np.sqrt(2 * k_val * id_val) if id_val > 0 else 0.0
    gds = lambda_param * id_val if enable_clm else 0.0

    return id_val, gm, gds, vth


def run_non_ideal_engine(
    gate_length_nm: float = 180.0,
    gate_width_um: float = 1.0,
    tox_nm: float = 4.0,
    mu_0: float = 450.0,
    vth0: float = 0.4,
    gamma: float = 0.4,
    phi2f: float = 0.6,
    lambda_param: float = 0.05,
    enable_body_effect: bool = True,
    enable_clm: bool = True,
    enable_velocity_saturation: bool = False,
    sweep_param: str = "vds",
    sweep_start: float = 0.0,
    sweep_end: float = 1.8,
    steps: int = 50,
    fixed_vgs: float = 1.8,
    fixed_vds: float = 1.2,
    fixed_vsb: float = 0.0,
    temp_c: float = 27.0,
) -> Dict[str, Any]:
    eps_ox = 3.9 * 8.854e-14
    tox_cm = tox_nm * 1e-7
    c_ox = eps_ox / tox_cm

    w_cm = gate_width_um * 1e-4
    l_cm = gate_length_nm * 1e-7

    sweep_vec = np.linspace(sweep_start, sweep_end, steps + 1)

    vds_list, vgs_list, vsb_list, temp_list = [], [], [], []
    id_list, vth_list, gm_list, gds_list, ron_list = [], [], [], [], []

    for val in sweep_vec:
        vgs = val if sweep_param == "vgs" else fixed_vgs
        vds = val if sweep_param == "vds" else fixed_vds
        vsb = val if sweep_param == "vsb" else fixed_vsb
        current_temp = val if sweep_param == "temp" else temp_c

        temp_k = current_temp + 273.15
        mu_temp = mu_0 * ((300.0 / temp_k) ** 1.5)
        k_val = mu_temp * c_ox * (w_cm / l_cm)

        id_val, gm, gds, vth = calculate_non_ideal_current(
            vgs, vds, vsb, current_temp, vth0, k_val, mu_temp, l_cm,
            lambda_param, gamma, phi2f, enable_body_effect, enable_clm, enable_velocity_saturation
        )

        vds_list.append(float(vds))
        vgs_list.append(float(vgs))
        vsb_list.append(float(vsb))
        temp_list.append(float(current_temp))
        id_list.append(float(id_val))
        vth_list.append(float(vth))
        gm_list.append(float(gm))
        gds_list.append(float(gds))
        ron_list.append(float(1.0 / gds) if gds > 0 else 1.0e6)

    return {
        "vds": vds_list,
        "vgs": vgs_list,
        "vsb": vsb_list,
        "temp_c": temp_list,
        "id": id_list,
        "vth": vth_list,
        "gm": gm_list,
        "gds": gds_list,
        "ron": ron_list,
        "sweep_param": sweep_param,
        "description": "Non-ideal square-law MOSFET model including body effect, CLM, and optional velocity saturation.",
    }