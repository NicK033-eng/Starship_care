import os

# --- PATH CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INBOUND_DIR = os.path.join(BASE_DIR, "outputs", "inbound") # Cartella generica per le fonti
OUTBOUND_DIR = os.path.join(BASE_DIR, "outputs", "outbound_reports")

# --- SALESFORCE HEADERS MAPPING ---
# Header esatti del CSV Salesforce → campo del modello Lead
SF_HEADERS_MAPPING = {
    "OrdinaNome e cognome":                          "nome_cognome",
    "OrdinaSocietà":                                 "societa",
    "OrdinaSociet�":                                 "societa",
    "OrdinaQualifica":                               "qualifica",
    "OrdinaStato/Provincia":                         "stato_provincia",
    "OrdinaTelefono":                                "telefono",
    "OrdinaEmail":                                   "email",
    "OrdinaStato lead":                              "stato_salesforce",
    "OrdinaData creazioneIn ordine decrescente":     "data_creazione_sf",
}

# Campi composti — costruiti via codice nel service
SF_TITOLARE_NOME    = "OrdinaNome titolare"
SF_TITOLARE_COGNOME = "OrdinaCognome titolare"

# --- SECONDA SOURCE HEADERS MAPPING ---
SECOND_SOURCE_HEADERS_MAPPING = {
    "azienda": "societa",
    "provincia": "stato_provincia",
    "fatturato": "fatturato",
    "citta": "citta", # Non mappato direttamente, ma può essere utile
    "source": "provenance"
}

# --- STATI ESITAZIONE OPERATORE ---
STATI_ESITAZIONE = [
    "Nuovo",
    "Action",
    "Red Flag",
    "Opec assegnato opp",
    "Offerta Inviata",
    "Action postponed",
]

# --- ICONE STATI ESITAZIONE ---
STATUS_ICONS = {
    "Nuovo":                "🆕",
    "Action":               "📧",
    "Red Flag":             "🚩",
    "Opec assegnato opp":   "💼",
    "Offerta Inviata":      "📨",
    "Action postponed":     "📅",
}
