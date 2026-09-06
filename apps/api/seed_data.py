import random

from app.db.database import SessionLocal
from app.db.models import MeasurementData


def generate_noisy_iv_curve(vds_fixed: float = 1.2, num_points: int = 61):
    # Generates a Vgs sweep at fixed Vds, with slight Gaussian noise
    # to mimic real physical silicon anomalies.
    # empirical_engine.py interpolates ACROSS Vgs, so Vgs must vary here.
    measurements = []
    vth = 0.4
    k_val = 350e-6  # ~physically reasonable k' * (W/L), gives currents in amp range

    for i in range(num_points):
        vgs = i * (1.8 / (num_points - 1))

        if vgs <= vth:
            id_ideal = 0.0
        elif vds_fixed < (vgs - vth):
            id_ideal = k_val * ((vgs - vth) * vds_fixed - 0.5 * (vds_fixed ** 2))
        else:
            id_ideal = 0.5 * k_val * ((vgs - vth) ** 2)

        # Add channel-length modulation and random hardware noise (amp-scale noise)
        id_real = id_ideal * (1 + 0.05 * vds_fixed) + random.gauss(0, 25e-6)
        id_real = max(0.0, id_real)  # Prevent impossible negative currents

        measurements.append({
            "vgs": float(vgs),
            "vds": float(vds_fixed),
            "id_measured": float(id_real),
        })

    return measurements


def seed_database():
    db = SessionLocal()

    existing = (
        db.query(MeasurementData)
        .filter(MeasurementData.chip_name == "NMOS_Test_Chip_01")
        .first()
    )
    if existing:
        print("INFO: NMOS_Test_Chip_01 already seeded, skipping.")
        db.close()
        return

    raw_data = generate_noisy_iv_curve()

    for data in raw_data:
        m_record = MeasurementData(
            chip_name="NMOS_Test_Chip_01",
            vgs=data["vgs"],
            vds=data["vds"],
            id_measured=data["id_measured"],
        )
        db.add(m_record)

    db.commit()
    db.close()

    print("SUCCESS: Seeded the database with NMOS_Test_Chip_01 measurements!")


if __name__ == "__main__":
    seed_database()