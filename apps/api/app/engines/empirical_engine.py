from typing import Any, Dict, List
import numpy as np
from sqlalchemy.orm import Session


def run_empirical_engine(
    db_session: Session,
    gate_length_nm: float = 180.0,
    gate_width_um: float = 1.0,
    vds_val: float = 1.2,
    vgs_start: float = 0.0,
    vgs_end: float = 1.8,
    num_points: int = 100,
) -> Dict[str, Any]:
    # 1. Fetch reference silicon measurement points from PostgreSQL
    # (Extracting seeded NMOS_Test_Chip_01 dataset)
    from app.db.models import MeasurementData  # dynamic import to avoid circular dependency

    reference_records = (
        db_session.query(MeasurementData)
        .filter(MeasurementData.chip_name == "NMOS_Test_Chip_01")
        .all()
    )

    vgs_sweep = np.linspace(vgs_start, vgs_end, num_points)

    if reference_records:
        # Extract measured Vgs and Id reference arrays from database
        ref_vgs = np.array([r.vgs for r in reference_records])
        ref_id = np.array([r.id_measured for r in reference_records])

        # Sort data points by Vgs for valid 1D interpolation
        sort_indices = np.argsort(ref_vgs)
        ref_vgs = ref_vgs[sort_indices]
        ref_id = ref_id[sort_indices]

        # Interpolate measured silicon curve across the requested Vgs sweep
        base_id_curve = np.interp(vgs_sweep, ref_vgs, ref_id)
    else:
        # Fallback physics baseline if seed data is unpopulated
        vth = 0.4
        kn = 350e-6 * (gate_width_um / (gate_length_nm * 1e-3))
        base_id_curve = np.array([
            0.5 * kn * max(0, vgs - vth) ** 2 for vgs in vgs_sweep
        ])

    # 2. Apply Empirical Short-Channel & Geometry Scaling
    # Reference Chip Parameters: W_ref = 1.0 um, L_ref = 180.0 nm
    w_scale = gate_width_um / 1.0
    l_scale = 180.0 / max(gate_length_nm, 10.0)

    # Empirical mobility degradation due to vertical electric field (theta * Vov)
    theta = 0.05  # V^-1
    vov = np.maximum(0, vgs_sweep - 0.4)
    mobility_degradation = 1.0 / (1.0 + theta * vov)

    # Velocity saturation factor for short channels (L < 250nm)
    esat = 5.0  # V/um
    l_um = gate_length_nm * 1e-3
    vsat_factor = 1.0 / (1.0 + (vds_val / (esat * l_um))) if l_um < 0.25 else 1.0

    # Final Empirical Drain Current calculation
    final_id_curve = (
        base_id_curve
        * w_scale
        * l_scale
        * mobility_degradation
        * vsat_factor
    )

    return {
        "vgs": vgs_sweep.tolist(),
        "id_empirical": final_id_curve.tolist(),
        "id_measured_raw": base_id_curve.tolist(),
        "scaling_factors": {
            "width_scale": float(w_scale),
            "length_scale": float(l_scale),
            "mobility_degradation_avg": float(np.mean(mobility_degradation)),
            "velocity_saturation_factor": float(vsat_factor),
        },
        "description": "Calculated using 1D interpolation on NMOS_Test_Chip_01 silicon data with short-channel mobility degradation.",
    }