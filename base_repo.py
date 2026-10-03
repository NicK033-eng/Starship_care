from sqlalchemy.orm import Session


class BaseRepository:
    """Repository base con operazioni CRUD generiche."""

    def __init__(self, model, db: Session):
        self.model = model
        self.db    = db

    def get_by_id(self, record_id):
        return self.db.query(self.model).filter(
            self.model.__table__.primary_key.columns.values()[0] == record_id
        ).first()

    def get_all(self):
        return self.db.query(self.model).all()

    def add(self, obj):
        self.db.add(obj)
        self.db.flush()  # assegna l'id senza commit definitivo
        return obj

    def delete(self, obj):
        self.db.delete(obj)
        self.db.flush()

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()
