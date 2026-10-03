from core.database import SessionLocal
from service.lead_service import scan_and_import_csv

db = SessionLocal()
try:
    result = scan_and_import_csv(db)
    print(f"File analizzati: {result['file_letti']}")
    print(f"Nuove Lead: {result['nuovi']}")
    print(f"Conflitti tracciati in nota: {result['conflitti_duplicati']}")
finally:
    db.close()
