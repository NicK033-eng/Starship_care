import sys
import os
import importlib
from datetime import datetime
import pandas as pd

# Aggiunge la root del progetto al path in modo che gli import funzionino
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_ROOT = os.path.join(ROOT, "service")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if SERVICE_ROOT not in sys.path:
    sys.path.insert(0, SERVICE_ROOT)
importlib.invalidate_caches()

import streamlit as st
from core.database import get_db, init_db
from models.lead_model import Lead
from repositories.lead_repo import LeadRepository
from service.lead_service import scan_and_import_csv, import_csv_file
from config import STATI_ESITAZIONE, STATUS_ICONS, OUTBOUND_DIR, INBOUND_DIR

# ------------------------------------------------------------------ #
# Inizializzazione e Configurazione Estetica Avanzata                #
# ------------------------------------------------------------------ #
st.set_page_config(page_title="CRM Lead Manager", layout="wide", page_icon="🎯")

# CSS personalizzato per compattare l'interfaccia, i KPI e bloccare le animazioni in alto a destra
st.markdown("""
    <style>
    /* Rimozione delle animazioni di caricamento di Streamlit (running/swimming icons) */
    div[data-testid="stStatusWidget"] {
        visibility: hidden;
        display: none !important;
    }
    
    /* Riduzione dei margini dei container delle lead per visualizzarne di più */
    div[data-testid="stContainer"] {
        padding: 0.4rem 0.8rem !important;
        margin-bottom: 0.2rem !important;
    }
    
    /* Stile per miniaturizzare i testi dei KPI */
    div[data-testid="stMetricValue"] {
        font-size: 1.1rem !important;
        font-weight: bold !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.75rem !important;
        color: #666666 !important;
    }
    
    /* Compattazione delle altezze dei campi di input e text area */
    div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea {
        padding: 4px 8px !important;
        font-size: 0.85rem !important;
    }
    
    /* Ottimizzazione altezze bottoni */
    div.stButton > button {
        padding: 2px 10px !important;
        height: auto !important;
        font-size: 0.85rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# Session state per logging operazioni
if "session_log" not in st.session_state:
    st.session_state.session_log = []
    st.session_state.session_start = datetime.now()

def log_operation(operation_type: str, details: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "operation": operation_type,
        "details": details
    }
    st.session_state.session_log.append(log_entry)

def export_session_log():
    if not st.session_state.session_log:
        st.warning("Nessuna operazione da esportare.")
        return
    
    df_log = pd.DataFrame(st.session_state.session_log)
    timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTBOUND_DIR, f"session_log_{timestamp_file}.csv")
    
    os.makedirs(OUTBOUND_DIR, exist_ok=True)
    df_log.to_csv(filename, index=False, encoding="utf-8-sig", sep=";")
    
    st.success(f"✅ Log esportato: {os.path.basename(filename)}")
    log_operation("EXPORT", f"Session log esportato in {os.path.basename(filename)}")
    return filename

# Inizializzazione DB
init_db()
db = next(get_db())
repo = LeadRepository(db)

# ------------------------------------------------------------------ #
# FUNZIONI DI CARICAMENTO DATI IN CACHE (OTTIMIZZAZIONE)             #
# ------------------------------------------------------------------ #

# Mettiamo in cache il caricamento di tutte le lead.
# La cache viene invalidata dopo 10 minuti o quando i dati cambiano.
@st.cache_data(ttl=600)
def load_all_leads(_repo):
    return _repo.get_all_ordered()

# Mettiamo in cache anche i conteggi per i KPI.
@st.cache_data(ttl=600)
def load_kpi_counts(_repo):
    return _repo.count_by_stato(), _repo.count_total()

@st.cache_data(ttl=300)
def get_cartelle_provenance(inbound_dir):
    try:
        if os.path.exists(inbound_dir) and os.path.isdir(inbound_dir):
            return [d for d in os.listdir(inbound_dir) if os.path.isdir(os.path.join(inbound_dir, d))]
    except Exception:
        pass
    return []


# ------------------------------------------------------------------ #
# SIDEBAR: Gestione File, Log e Barra Filtri Verticale Retrattile    #
# ------------------------------------------------------------------ #
with st.sidebar:
    st.title("⭐ CRM Panel")
    
    with st.expander("📁 Importazione Dati Salesforce", expanded=False):
        uploaded_file = st.file_uploader(
            "Carica CSV Salesforce",
            type=["csv"],
            help="Carica un file CSV esportato da Salesforce.",
            label_visibility="collapsed"
        )

        if uploaded_file is not None:
            if st.button("📤 Importa File", use_container_width=True):
                with st.spinner("Importazione..."):
                    # Per l'upload singolo, la provenienza è generica
                    res = import_csv_file(uploaded_file, uploaded_file.name, db, provenance="upload_manuale")
                if res.get("errori"):
                    st.error("Errore durante l'importazione.")
                    for err in res["errori"]:
                        st.write(f"- {err}")
                else:
                    st.success("Completato!")
                    # Pulisce la cache per forzare il ricaricamento dei dati aggiornati
                    st.cache_data.clear()
                    st.rerun()

        if st.button("🔄 Carica Cartella Inbound", use_container_width=True):
            with st.spinner("Analisi cartella..."):
                res = scan_and_import_csv(db)
            st.success("Sincronizzazione completata!")
            # Pulisce la cache per forzare il ricaricamento dei dati aggiornati
            st.cache_data.clear()
            st.rerun()
            
        if st.button("📊 Esporta Log Sessione", use_container_width=True, type="secondary"):
            export_session_log()

    st.markdown("---")
    
    # 2) NUOVA BARRA FILTRI VERTICALE RETRATTILE
    st.header("🔍 Filtri Ricerca")
    
    azienda_search = st.text_input(
        "Filtra per Società:",
        value="",
        placeholder="Scrivi il nome azienda...",
    )
    
    st.markdown("**Stati Esitazione:**")
    filtro_stati = []
    for stato in STATI_ESITAZIONE:
        icon = STATUS_ICONS.get(stato, "•")
        if st.checkbox(f"{icon} {stato}", value=True, key=f"filter_{stato}"):
            filtro_stati.append(stato)

    # Filtro per provenienza
    # Legge le provenienze reali presenti nel database
    provenienze_db = repo.get_distinct_provenances()
    provenienze = ["Tutte"] + sorted(provenienze_db)
    provenienza_selezionata = st.selectbox(
        "Filtra per Fonte:",
        options=provenienze,
        index=0,
    )

    if not filtro_stati:
        filtro_stati = STATI_ESITAZIONE

# --- Caricamento e filtraggio dati OTTIMIZZATO con CACHE ---

# 1. Carichiamo TUTTE le lead dalla cache (la query al DB viene fatta solo se la cache è vuota/scaduta)
all_leads = load_all_leads(repo)
lead_filtrate = all_leads

# 2. Applichiamo i filtri in memoria sulla lista di lead, non sul database
if azienda_search:
    search_term = azienda_search.strip().lower()
    lead_filtrate = [
        lead for lead in lead_filtrate 
        if lead.societa and search_term in lead.societa.lower()
    ]

if provenienza_selezionata != "Tutte":
    lead_filtrate = [
        lead for lead in lead_filtrate 
        if lead.provenance == provenienza_selezionata
    ]

if filtro_stati:
    lead_filtrate = [
        lead for lead in lead_filtrate 
        if lead.stato_esitazione in filtro_stati
    ]

# ------------------------------------------------------------------ #
# MAIN PANEL: Header, KPI Compatti e Coda Lead                      #
# ------------------------------------------------------------------ #

# Titolo minimale e compatto
st.markdown("<h3 style='margin: 0; padding-bottom: 5px; font-weight: normal;'>gestionale lead di Nicola</h3>", unsafe_allow_html=True)

# Carichiamo i conteggi per i KPI dalla cache
conteggi, totale = load_kpi_counts(repo)

# 3) SEZIONE KPI COMPATTA IN UN RIQUADRO LEGGERO
with st.container(border=True):
    kpi_cols = st.columns(len(STATI_ESITAZIONE) + 1)
    kpi_cols[0].metric("📊 Totale", totale)
    for idx, stato in enumerate(STATI_ESITAZIONE):
        icon = STATUS_ICONS.get(stato, "•")
        kpi_cols[idx + 1].metric(f"{icon} {stato}", conteggi.get(stato, 0))

st.markdown("<div style='margin: 5px 0;'></div>", unsafe_allow_html=True)

if not lead_filtrate:
    st.info("Nessuna lead trovata corrispondente ai criteri selezionati.", icon="ℹ️")
else:
    # 1) CODA LEAD MICRO-COMPATTA (Almeno 5 o più lead visibili per pagina)
    for lead in lead_filtrate:
        with st.container(border=True):
            
            # Riga 1: Dati Identificativi Principali (Anagrafica Rapida in Sola Lettura)
            info_col1, info_col2, info_col3, info_col4, info_col5 = st.columns([3, 2, 2, 2, 1.5])
            with info_col1:
                st.markdown(f"🏢 **{lead.societa or '—'}**")
                if lead.nome_cognome:
                    st.markdown(f"👤 {lead.nome_cognome}")
            with info_col2:
                st.markdown(f"✉️ `{lead.email}`")
                if lead.fatturato:
                    st.markdown(f"💰 **{lead.fatturato}**")
            with info_col3:
                st.caption(f"📞 {lead.telefono or '—'}")
            with info_col4:
                st.caption(f"🏙️ Prov: {lead.stato_provincia or '—'}")
            with info_col5:
                icon = STATUS_ICONS.get(lead.stato_esitazione, "•")
                st.markdown(f"**{icon} {lead.stato_esitazione}**")
                
            # Riga 2: Campi di Editing e Note Allineati e Ridotti
            edit_col_note, edit_col_log, edit_col_azione = st.columns([5, 5, 2])
            
            with edit_col_note:
                nuova_nota_op = st.text_area(
                    "Note Personali",
                    value=lead.nota_operatore or "",
                    height=52,
                    key=f"nota_{lead.email}",
                    label_visibility="collapsed",
                    placeholder="Aggiungi note personali..."
                )
            
            with edit_col_log:
                st.text_area(
                    "Log Importazione",
                    value=lead.note_import or "",
                    height=52,
                    disabled=True,
                    key=f"log_{lead.email}",
                    label_visibility="collapsed",
                    placeholder="Nessun log di importazione."
                )
            
            with edit_col_azione:
                idx_stato = (
                    STATI_ESITAZIONE.index(lead.stato_esitazione)
                    if lead.stato_esitazione in STATI_ESITAZIONE
                    else 0
                )
                nuovo_stato = st.selectbox(
                    "Cambia Stato",
                    options=STATI_ESITAZIONE,
                    index=idx_stato,
                    key=f"stato_{lead.email}",
                    label_visibility="collapsed",
                )
                
                if st.button("💾 Salva", key=f"save_{lead.email}", use_container_width=True):
                    repo.update_esitazione(
                        email          = lead.email,
                        nuovo_stato    = nuovo_stato,
                        nota_operatore = nuova_nota_op,
                        nome_cognome   = lead.nome_cognome,
                        societa        = lead.societa,
                    )
                    db.commit()
                    log_operation("UPDATE_LEAD", f"{lead.societa} ({lead.email}) → {nuovo_stato}")
                    st.toast("✅ Salvato!", icon="✅")
                    # Pulisce la cache per forzare il ricaricamento dei dati aggiornati
                    st.cache_data.clear()
                    st.rerun()