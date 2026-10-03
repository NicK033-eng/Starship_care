from sqlalchemy import Column, String, Text, DateTime
from datetime import datetime
from core.database import Base


class Lead(Base):
    __tablename__ = "leads"

    # Chiave primaria: email (FIX: primary_key=True, non primary_base)
    # Le lead senza email vengono gestite con un ID sintetico nel service
    email = Column(String, primary_key=True, index=True)

    # Campi anagrafici dal CSV Salesforce
    nome_cognome     = Column(String,   nullable=True)
    societa          = Column(String,   nullable=True, index=True)
    qualifica        = Column(String,   nullable=True)
    stato_provincia  = Column(String,   nullable=True)
    telefono         = Column(String,   nullable=True)
    stato_salesforce = Column(String,   nullable=True)  # "SortStato lead"
    titolare         = Column(String,   nullable=True)  # Nome + Cognome titolare
    data_creazione_sf = Column(String,  nullable=True)  # data creazione originale SF

    # Campi gestiti dall'operatore / applicazione
    fatturato         = Column(String,   nullable=True)
    stato_esitazione  = Column(String, default="Nuovo", index=True)
    nota_operatore    = Column(Text,   default="")
    note_import       = Column(Text,   default="")       #Log automatico import/duplicati
    provenance        = Column(String, nullable=True, index=True)    # Provenienza: "inbound_salesforces" o "inbound_other"
    data_aggiornamento = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )

    def __repr__(self):
        return f"<Lead email={self.email!r} societa={self.societa!r} stato={self.stato_esitazione!r}>"
