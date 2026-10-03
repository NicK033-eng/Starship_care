import streamlit as st
from core.database import get_db # La tua funzione di connessione DB
from service.lead_service import scan_and_import_csv

st.set_page_config(layout="wide")
st.title("Lead Board & KPI Control")

# Otteniamo la sessione del database
db = next(get_db())

# Pulsante manuale per forzare il controllo della cartella o esecuzione automatica all'avvio
if st.sidebar.button("Importa CSV da /outputs"):
    with st.spinner("upload in corso..."):
        risultato = scan_and_import_csv(db)
        st.sidebar.success(f"upload completato!")
        st.sidebar.write(f"📁 File analizzati: {risultato['file_letti']}")
        st.sidebar.write(f"🆕 Nuove Lead: {risultato['nuovi']}")
        st.sidebar.write(f"📝 Conflitti tracciati in nota: {risultato['conflitti_duplicati']}")
# Query sul DB per mostrare le lead caricate...