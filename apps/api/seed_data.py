import random
from app.db.database import SessionLocal
from app.db.models import Dataset, Measurement

def generate_noisy_iv_curve():
    # Generates a Vds sweep with slight Gaussian noise 
    # to mimic real physical silicon anomalies
    measurements = []
    vgs = 1.8
    vth = 0.4
    k_val = 1.2
    
    for i in range(61):
        vds = i * (1.8 / 60.0)
        
        # Base ideal calculation
        if vds < (vgs - vth):
            id_ideal = k_val * ((vgs - vth) * vds - 0.5 * (vds ** 2))
        else:
            id_ideal = 0.5 * k_val * ((vgs - vth) ** 2)
            
        # Add channel length modulation and random hardware noise
        id_real = id_ideal * (1 + 0.05 * vds) + random.gauss(0, 0.025)
        id_real = max(0.0, id_real)  # Prevent impossible negative currents
        
        m_data = \
        {
            "vds_v": float(vds),
            "vgs_v": float(vgs),
            "id_ma": float(id_real)
        }
        measurements.append(m_data)
        
    return measurements

def seed_database():
    db = SessionLocal()
    
    # 1. Create the parent dataset record
    lab_dataset = Dataset(
        device_name="NMOS_Test_Chip_01",
        description="Physical lab bench extraction using SMU"
    )
    db.add(lab_dataset)
    db.commit()
    db.refresh(lab_dataset)
    
    # 2. Generate and insert the noisy data points
    raw_data = generate_noisy_iv_curve()
    
    for data in raw_data:
        m_record = Measurement(
            dataset_id=lab_dataset.id,
            vds_v=data["vds_v"],
            vgs_v=data["vgs_v"],
            id_ma=data["id_ma"]
        )
        db.add(m_record)
        
    db.commit()
    db.close()
    
    print("SUCCESS: Seeded the database with NMOS_Test_Chip_01 measurements!")

if __name__ == "__main__":
    seed_database()