from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models.lead_model import Lead
from repositories.base_repo import BaseRepository
from config import STATI_ESITAZIONE


def upsert_leads(session, lead_dicts):
    for data in lead_dicts:
        stmt = insert(Lead).values(data)
        # Se c'è conflitto sulla chiave unica, aggiorna i dati di esitazione o di contatto
        stmt = stmt.on_conflict_do_update(
            constraint='_email_company_uc',
            set_={
                'first_name': stmt.excluded.first_name,
                'last_name': stmt.excluded.last_name,
                'status': stmt.excluded.status 
            }
        )
        session.execute(stmt)
    session.commit()


class LeadRepository(BaseRepository):
    """Query specifiche per la tabella leads."""

    def __init__(self, db: Session):
        super().__init__(Lead, db)

    # ------------------------------------------------------------------ #
    # Ricerca                                                              #
    # ------------------------------------------------------------------ #

    def get_by_email(self, email: str) -> Lead | None:
        return self.db.query(Lead).filter(Lead.email == email.lower().strip()).first()

    def get_by_societa(self, societa: str) -> Lead | None:
        if not societa or societa.strip() == "":
            return None
        normalized = societa.lower().strip()
        return (
            self.db.query(Lead)
            .filter(
                Lead.societa.isnot(None),
                func.lower(func.trim(Lead.societa)) == normalized
            )
            .first()
        )

    def get_all_ordered(self, provenance: str = None) -> list[Lead]:
        """Tutte le lead, dalla più recente, opzionalmente filtrate per provenienza."""
        query = self.db.query(Lead)
        if provenance:
            query = query.filter(Lead.provenance == provenance)
        return (
            query
            .order_by(Lead.data_aggiornamento.desc())
            .all()
        )

    def get_by_stato_esitazione(self, stato: str) -> list[Lead]:
        return self.db.query(Lead).filter(Lead.stato_esitazione == stato).all()

    def count_by_stato(self) -> dict[str, int]:
        """Dizionario {stato: conteggio} per i KPI della dashboard."""
        result = {}
        for stato in STATI_ESITAZIONE:
            result[stato] = (
                self.db.query(Lead)
                .filter(Lead.stato_esitazione == stato)
                .count()
            )
        return result

    def count_total(self) -> int:
        return self.db.query(Lead).count()

    def get_distinct_provenances(self) -> list[str]:
        """Restituisce una lista di tutte le `provenance` uniche presenti nel database."""
        results = self.db.query(Lead.provenance).distinct().all()
        return [r[0] for r in results if r[0] is not None]

    # ------------------------------------------------------------------ #
    # Inserimento / aggiornamento                                          #
    # ------------------------------------------------------------------ #

    def insert(self, lead: Lead) -> Lead:
        self.db.add(lead)
        self.db.flush()
        return lead

    def update_esitazione(self, email: str, nuovo_stato: str,
                           nota_operatore: str, nome_cognome: str,
                           societa: str) -> Lead | None:
        lead = self.get_by_email(email)
        if not lead:
            return None
        lead.stato_esitazione = nuovo_stato
        lead.nota_operatore   = nota_operatore
        lead.nome_cognome     = nome_cognome
        lead.societa          = societa
        self.db.flush()
        return lead