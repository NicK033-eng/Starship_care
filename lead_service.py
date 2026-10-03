import io
import os
import glob
import uuid
import hashlib
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session

from models.lead_model import Lead
from repositories.lead_repo import LeadRepository
from config import (
    INBOUND_DIR,
    SF_TITOLARE_NOME,
    SF_TITOLARE_COGNOME,
    SF_HEADERS_MAPPING,
    SECOND_SOURCE_HEADERS_MAPPING,
)


# ------------------------------------------------------------------ #
# Utility                                                              #
# ------------------------------------------------------------------ #

def _normalizza_telefono(val) -> str:
    """
    Converte la notazione scientifica che Excel genera sui numeri lunghi.
    Es. "3,93471E+11" -> "393471000000"
    Restituisce stringa vuota se non convertibile.
    """
    if val is None:
        return ""
    # Normalizzazione per la deduplica: rimuove punteggiatura, spazi e normalizza forme societarie
    s = str(val).strip().lower()
    s = s.replace(".", "").replace(",", "").replace("-", " ")
    s = s.replace("srl", "s.r.l.").replace("spa", "s.p.a.")
    # Rimuove spazi multipli
    s = " ".join(s.split())
    return s


def _normalize_societa(val) -> str:
    """Normalizza il campo societa per la deduplica."""
    if val is None:
        return ""
    return str(val).strip().lower()


def _genera_email_sintetica(row: pd.Series, filename: str, idx: int) -> str:
    """
    Per le lead senza email crea una chiave primaria sintetica deterministica.
    Usa nome, societa e telefono per mantenere lo stesso identificatore tra importazioni.
    """
    nome = str(row.get("nome_cognome", "") or "").strip().lower()
    societa = str(row.get("societa", "") or "").strip().lower()
    telefono = _normalizza_telefono(row.get("telefono", ""))

    key = f"{nome}|{societa}|{telefono}"
    if not key.strip("|"):
        # Se proprio non c'è nessun campo utile, usiamo comunque un identificatore fallback.
        key = f"missing|{filename}|{idx}"

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"noemail_{digest}@synthetic.local"

def _genera_email_sintetica_second_source(row: pd.Series, filename: str, idx: int) -> str:
    """
    Genera una chiave primaria sintetica per la seconda fonte di dati.
    """
    societa = str(row.get("societa", "") or "").strip().lower()
    provincia = str(row.get("stato_provincia", "") or "").strip().lower()
    key = f"{societa}|{provincia}"
    if not key.strip("|"):
        key = f"missing_ss|{filename}|{idx}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"noemail_ss_{digest}@synthetic.local"


def _leggi_csv(file_path: str) -> pd.DataFrame:
    """Legge il CSV gestendo encoding e separatore variabile (prima ; e poi ,)."""
    with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        first_line = f.readline()
    
    sep = ";" if ";" in first_line else ","

    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            df = pd.read_csv(file_path, sep=sep, encoding=enc, engine='python')
            df.columns = [c.strip() for c in df.columns]
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Impossibile decodificare il file: {file_path}")


def _load_csv_from_buffer(file_bytes: bytes) -> pd.DataFrame:
    """Legge un CSV da un buffer in memoria, gestendo separatore variabile."""
    try:
        first_line = file_bytes.splitlines(keepends=False)[0].decode("utf-8-sig")
    except (IndexError, UnicodeDecodeError):
        first_line = ""

    sep = ";" if ";" in first_line else ","
    
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, engine='python')
            df.columns = [c.strip() for c in df.columns]
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError("Impossibile decodificare il CSV caricato.")


def _process_dataframe_sf(df: pd.DataFrame, filename: str, repo: LeadRepository, report: dict, provenance: str) -> None:
    # Rinomina le colonne utilizzando la mappa da config.py
    df = df.rename(columns=SF_HEADERS_MAPPING)

    # Rinomina la funzione originale per chiarezza
    if "societa" not in df.columns:
        return

    # Carica tutte le società già presenti nel database in memoria
    existing_societa_set = set()
    for lead in repo.get_all_ordered():
        if lead.societa:
            normalized = _normalize_societa(lead.societa)
            if normalized:
                existing_societa_set.add(normalized)

    # Verifica se esiste la colonna priorità per il mapping dello stato
    has_priorita = "priorità" in df.columns or "Priorità" in df.columns
    priorita_col = "priorità" if "priorità" in df.columns else ("Priorità" if "Priorità" in df.columns else None)

    df["societa_norm"] = (
        df["societa"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    df = df.drop_duplicates(subset=["societa_norm"], keep="last").reset_index(drop=True)

    df["email"] = (
        df.get("email", pd.Series([""] * len(df)))
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    skipped_count = 0
    for idx, row in df.iterrows():
        societa_raw = str(row.get("societa", "") or "").strip()
        societa_norm = _normalize_societa(societa_raw)
        
        # Se la società è già nel database, saltiamo tutta la riga
        if societa_norm and societa_norm in existing_societa_set:
            report["conflitti_duplicati"] += 1
            skipped_count += 1
            continue

        email_raw = row.get("email", "")
        if not email_raw or email_raw == "nan":
            report["skippati_no_email"] += 1
            email_lead = _genera_email_sintetica(row, filename, idx)
        else:
            email_lead = email_raw

        titolare = (
            f"{row.get(SF_TITOLARE_NOME, '') or ''} "
            f"{row.get(SF_TITOLARE_COGNOME, '') or ''}".strip()
        )
        telefono = _normalizza_telefono(row.get("telefono", ""))

        # Determina lo stato_esitazione basato sulla priorità
        # Solo il valore 2 mappa ad Action, 3 a Red Flag, tutti gli altri casi sono Nuovo.
        stato_esitazione = "Nuovo"
        if has_priorita and priorita_col:
            try:
                priorita = int(row.get(priorita_col, 0))
                if priorita == 3:
                    stato_esitazione = "Red Flag"
                elif priorita == 2:
                    stato_esitazione = "Action"
                else:
                    stato_esitazione = "Nuovo"
            except (ValueError, TypeError):
                stato_esitazione = "Nuovo"

        # Se arriviamo qui, la società non è un duplicato, quindi creiamo il nuovo Lead
        def s(col):
            v = str(row.get(col, "") or "").strip()
            return v if v else None

        nuova = Lead(
            email             = email_lead,
            nome_cognome      = s("nome_cognome"),
            societa           = societa_raw if societa_raw else None,
            qualifica         = s("qualifica"),
            stato_provincia   = s("stato_provincia"),
            telefono          = telefono or None,
            stato_salesforce  = s("stato_salesforce"),
            titolare          = titolare or None,
            data_creazione_sf = s("data_creazione_sf"),
            stato_esitazione  = stato_esitazione,
            provenance        = provenance,
            note_import       = (
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M')}] "
                f"Importato da {os.path.basename(filename)} (Fonte: {provenance}).\n"
            ),
        )
        repo.insert(nuova)
        report["nuovi"] += 1
        # Aggiungi alla lista locale per le ricerche future nello stesso file
        if societa_norm:
            existing_societa_set.add(societa_norm)

def _process_dataframe_second_source(df: pd.DataFrame, filename: str, repo: LeadRepository, report: dict, provenance: str) -> None:
    """Processa il dataframe proveniente dalla seconda fonte dati."""
    # Rinomina le colonne utilizzando la mappa da config.py
    df = df.rename(columns=SECOND_SOURCE_HEADERS_MAPPING)

    if "societa" not in df.columns:
        return

    existing_societa_set = {_normalize_societa(lead.societa) for lead in repo.get_all_ordered() if lead.societa}

    df["societa_norm"] = df["societa"].fillna("").astype(str).apply(_normalize_societa)
    df = df.drop_duplicates(subset=["societa_norm"], keep="last").reset_index(drop=True)
    
    for idx, row in df.iterrows():
        societa_raw = str(row.get("societa", "") or "").strip()
        societa_norm = _normalize_societa(societa_raw)

        if societa_norm and societa_norm in existing_societa_set:
            report["conflitti_duplicati"] += 1
            continue

        email_lead = _genera_email_sintetica_second_source(row, filename, idx)
        
        nuova = Lead(
            email=email_lead,
            societa=societa_raw,
            stato_provincia=row.get("stato_provincia"),
            fatturato=row.get("fatturato"),
            stato_esitazione="Nuovo",
            provenance=provenance,
            note_import=(
                f"[{datetime.now().strftime('%d/%m/%Y %H:%M')}] "
                f"Importato da {os.path.basename(filename)} (Fonte: {provenance}).\n"
            ),
        )
        repo.insert(nuova)
        report["nuovi"] += 1
        if societa_norm:
            existing_societa_set.add(societa_norm)


# ------------------------------------------------------------------ #
# Funzione principale                                                  #
# ------------------------------------------------------------------ #

def scan_and_import_csv(db_session: Session) -> dict:
    """
    Scansiona tutte le sottocartelle di INBOUND_DIR. Ogni sottocartella rappresenta
    una 'provenance'. Importa tutti i CSV trovati.
    """
    repo = LeadRepository(db_session)
    report = {
        "file_letti": 0, "nuovi": 0, "conflitti_duplicati": 0, "skippati_no_email": 0
    }

    if not os.path.exists(INBOUND_DIR):
        os.makedirs(INBOUND_DIR)
        report["info"] = f"Cartella 'inbound' non esisteva, è stata creata."
        return report

    # Scansiona le sottocartelle che rappresentano le fonti (provenance)
    for provenance_folder in os.listdir(INBOUND_DIR):
        provenance_path = os.path.join(INBOUND_DIR, provenance_folder)
        if not os.path.isdir(provenance_path):
            continue

        csv_files = glob.glob(os.path.join(provenance_path, "*.csv"))
        report["file_letti"] += len(csv_files)

        for file_path in csv_files:
            try:
                df = _leggi_csv(file_path)
                
                # Determina il tipo di CSV e chiama il processore corretto
                if "OrdinaSociet�" in df.columns or "SortSocietà" in df.columns or "societa" in df.columns:
                    _process_dataframe_sf(df, file_path, repo, report, provenance=provenance_folder)
                elif "azienda" in df.columns:
                    _process_dataframe_second_source(df, file_path, repo, report, provenance=provenance_folder)

            except Exception as e:
                report.setdefault("errori", []).append(f"{os.path.basename(file_path)}: {e}")
                continue

    db_session.commit()
    return report


def import_csv_file(file_obj, filename: str, db_session: Session, provenance: str = "upload_manuale") -> dict:
    """Importa un CSV caricato dall'interfaccia, con provenienza opzionale."""
    report = {
        "file_letti":          1,
        "nuovi":               0,
        "conflitti_duplicati": 0,
        "skippati_no_email":   0,
    }
    repo = LeadRepository(db_session)
    try:
        content = file_obj.read() if hasattr(file_obj, "read") else file_obj
        df = _load_csv_from_buffer(content)
        
        # Determina il tipo di CSV e chiama il processore corretto
        if "OrdinaSociet�" in df.columns or "SortSocietà" in df.columns or "societa" in df.columns:
            _process_dataframe_sf(df, filename, repo, report, provenance=provenance)
        elif "azienda" in df.columns or "societa" in df.columns:
            _process_dataframe_second_source(df, filename, repo, report, provenance=provenance)
        else:
            raise ValueError("Formato CSV non riconosciuto. Intestazioni mancanti.")

    except Exception as e:
        report.setdefault("errori", []).append(str(e))
        db_session.rollback()
        return report

    db_session.commit()
    return report
