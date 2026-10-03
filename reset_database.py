"""
Script per resettare il database eliminando tutte le lead.
Uso: python reset_database.py
"""
from core.database import engine, SessionLocal, Base
from models.lead_model import Lead

def reset_database():
    """Elimina e ricrea la tabella delle lead."""
    try:
        # Elimina la tabella esistente
        print("ℹ️  Cancellazione della tabella 'leads' in corso...")
        Base.metadata.drop_all(bind=engine, tables=[Lead.__table__])
        
        # Ricrea la tabella basandosi sul modello aggiornato
        print("✨ Creazione della nuova tabella 'leads'...")
        Base.metadata.create_all(bind=engine, tables=[Lead.__table__])
        
        print("✅ Database resettato e tabella 'leads' ricreata con successo!")
    except Exception as e:
        print(f"❌ Errore durante il reset: {e}")

if __name__ == "__main__":
    reset_database()
