"""
Agente CLI di qualifica lead — Powered by Gemini
Qualifica lead 'Nuovo', recuperando dati aziendali online
e salvando un'analisi strutturata e sintetica nel campo nota_operatore.
"""
import os
import sys
import time
from datetime import datetime
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from dotenv import load_dotenv
from core.database import SessionLocal
from models.lead_model import Lead
from repositories.lead_repo import LeadRepository

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ---------------------------------------------------------------------------
# TOOL: Ricerca e Scraping (per verifica dati)
# ---------------------------------------------------------------------------

def cerca_web(query: str) -> list:
    """
    Cerca su DuckDuckGo e restituisce i primi 5 risultati.
    Utile per trovare il sito ufficiale o dati della Camera di Commercio.
    """
    try:
        print(f"  🔍 Ricerca web: {query}...")
        time.sleep(1) # Piccolo delay per non essere bloccati
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            return results
    except Exception as e:
        print(f"  ⚠️ Errore ricerca: {e}")
        return [f"Errore nella ricerca: {e}"]

def leggi_pagina_web(url: str) -> str:
    """
    Scarica il contenuto testuale di una pagina web.
    Utile per cercare il numero di telefono nella pagina contatti o nel footer.
    """
    try:
        print(f"  🌐 Lettura sito: {url}...")
        time.sleep(1) # Piccolo delay
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        text = soup.get_text(separator=' ')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        return text[:5000] # Limite per i token
    except Exception as e:
        print(f"  ⚠️ Errore lettura: {e}")
        return f"Errore nel caricamento della pagina: {e}"

# ---------------------------------------------------------------------------
# TOOL: recupero lead
# ---------------------------------------------------------------------------

def ottieni_lead_da_qualificare(limite: int = 15, provenance: str = None) -> list:
    db = SessionLocal()
    repo = LeadRepository(db)
    try:
        # Qualifichiamo solo lead con stato "Nuovo" per evitare di ripetere il lavoro.
        da_fare = (
            db.query(Lead)
            .filter(Lead.stato_esitazione == "Nuovo")
        )
        
        if provenance:
            da_fare = da_fare.filter(Lead.provenance == provenance)
            
        # Priorità: Leads meno recenti (per non ripetere sempre le stesse)
        da_fare = (
            da_fare
            .order_by(Lead.data_aggiornamento.asc())
            .limit(limite)
            .all()
        )

        return [
            {
                "e": l.email,
                "n": l.nome_cognome,
                "s": l.societa,
                "t": l.telefono,
                "p": l.stato_provincia,
            }
            for l in da_fare
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# TOOL: salvataggio analisi  (esposto a Gemini)
# ---------------------------------------------------------------------------

def salva_analisi_lead(
    email: str,
    settore: str,
    attivita: str,
    sito: str,
    tel_valido: bool,
    sito_trovato: bool,
    voto: int,
    note: str,
    telefono_scoperto: str = None,
) -> str:
    """
    Salva l'analisi strutturata di una lead nel database.

    Args:
        email:        Email della lead.
        settore:      Macro-settore (es. 'Manifatturiero', 'Retail', 'ICT', 'Edilizia').
        attivita:     Attività specifica dedotta dalla ragione sociale o dal sito
                      (es. 'Produzione stampi in plastica', 'E-commerce abbigliamento').
                      Usa 'N/D' se non determinabile.
        sito:         URL del sito trovato (es. 'www.azienda.it') oppure stringa vuota.
        tel_valido:   True se il numero ha formato italiano/internazionale plausibile.
        sito_trovato: True se è stato trovato un sito web attivo.
        voto:         Intero 0-10. Criteri: dati completi +3, attività identificata +3,
                      sito trovato +2, telefono valido +1, settore ad alto valore +1.
        note:         Max 25 parole. Includi info sulla visibilità del telefono se trovato sul sito.
        telefono_scoperto: Numero di telefono recuperato dal sito web (se trovato).
    """
    db = SessionLocal()
    repo = LeadRepository(db)
    try:
        # Assicuriamoci che voto sia un intero (Gemini a volte manda float)
        voto = int(voto)
        
        lead = repo.get_by_email(email)
        if not lead:
            return f"ERR: {email} non trovata."

        # Aggiorniamo il telefono se Gemini ne trova uno nuovo/migliore
        # (Sostituiamo se quello attuale è vuoto o se Gemini ne propone uno esplicito diverso)
        if telefono_scoperto and telefono_scoperto.strip() != "":
            nuovo_tel = telefono_scoperto.strip()
            if not lead.telefono or lead.telefono.strip() == "" or lead.telefono.strip() != nuovo_tel:
                lead.telefono = nuovo_tel

        # Mostriamo il numero nel log invece della semplice spunta
        tel_display = lead.telefono or "❌"
        sito_str = "✅" if sito_trovato else "❌"
        sito_display = sito or "—"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        riga = (
            f"[{now_str} AI] Settore: {settore} | Attività: {attivita} | "
            f"Sito: {sito_display} ({sito_str}) | Tel: {tel_display} | "
            f"Voto: {voto}/10 | Note: {note}"
        )

        nota_attuale = lead.nota_operatore or ""
        lead.nota_operatore = f"{nota_attuale}\n{riga}".strip()
        lead.qualifica = f"{settore} — {attivita}"
        lead.stato_esitazione = "Action"

        db.commit()
        print(f"  ✅ {email} → voto {voto}/10 | {settore} | attività: {attivita}")
        return "OK"
    except Exception as ex:
        db.rollback()
        return f"ERR DB: {ex}"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# SISTEMA DI PROMPT  (ottimizzato per la precisione del dato)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Ricevi lead italiane e devi qualificarle con MASSIMA PRECISIONE.

ITER DI VERIFICA OBBLIGATORIO PER OGNI LEAD:
1. RICERCA SITO: Usa 'cerca_web' per trovare il sito ufficiale della società.
2. VERIFICA CONTENUTO: Se trovi il sito, usa 'leggi_pagina_web' sulla Home o sulla pagina 'Contatti' per estrarre il telefono.
3. CROSS-CHECK CAMERA DI COMMERCIO/DIRECTORY: Usa 'cerca_web' cercando "[Nome Società] camera di commercio" o "[Nome Società] contatti".
   - Controlla snippet di siti come 'informazione-aziende.it', 'ufficiocamerale.it', 'paginebianche.it', 'paginegialle.it'.
4. COERENZA GEOGRAFICA:
   - Milano (MI) -> prefisso 02. Monza (MB) -> prefisso 039.
   - Se il numero non corrisponde alla provincia della lead (campo 'p'), verifica bene sul sito.
5. RAGIONE SOCIALE: Assicurati che il numero appartenga alla società indicata. Se hai il minimo dubbio (es. il numero appartiene a un'altra ditta nello stesso stabile o a un'agenzia), NON SALVARLO.

IMPORTANTE: Passa il telefono trovato nel campo 'telefono_scoperto'. Se NON sei sicuro, lascia il campo vuoto o metti None.
Meglio nessun numero che un numero sbagliato.

CHIAMA salva_analisi_lead PER OGNI LEAD. Nessuna eccezione.
"""

USER_TEMPLATE = """\
Qualifica queste {n} lead (formato: e=email, n=nome, s=società, t=telefono, p=provincia):
{leads}

Ordine di priorità: inizia dalle lead per cui riesci a identificare l'attività reale dalla ragione sociale.\
"""


# ---------------------------------------------------------------------------
# AGENTE
# ---------------------------------------------------------------------------

def esegui_agente(limite: int = 15, provenance: str = None) -> None:
    print("🤖 Agente qualifica lead avviato...")

    # Se non specificata, chiediamo all'utente
    if provenance is None:
        db = SessionLocal()
        repo = LeadRepository(db)
        fonti = repo.get_distinct_provenances()
        db.close()

        if fonti:
            print("\n📂 Fonti disponibili nel database:")
            print("0. Tutte le fonti")
            for i, f in enumerate(fonti, 1):
                print(f"{i}. {f}")
            
            scelta = input(f"\nScegli il numero della fonte (0-{len(fonti)}) [Default 0]: ").strip()
            if scelta.isdigit():
                idx = int(scelta)
                if 1 <= idx <= len(fonti):
                    provenance = fonti[idx-1]
                else:
                    provenance = None
            else:
                provenance = None

    leads = ottieni_lead_da_qualificare(limite=limite, provenance=provenance)
    if not leads:
        print("🎉 Nessuna lead da qualificare (Nuovo/Action).")
        return

    print(f"📦 {len(leads)} lead da processare" + (f" per fonte '{provenance}'...\n" if provenance else "...\n"))

    model = genai.GenerativeModel(
        model_name="gemini-flash-latest",
        tools=[salva_analisi_lead, cerca_web, leggi_pagina_web],
        system_instruction=SYSTEM_PROMPT,
    )

    chat = model.start_chat(enable_automatic_function_calling=True)
    prompt = USER_TEMPLATE.format(n=len(leads), leads=leads)
    response = chat.send_message(prompt)

    print("\n📋 Riepilogo:\n" + response.text)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agente CLI qualifica lead")
    parser.add_argument("--limite", type=int, default=15, help="Numero di lead da processare (default: 15)")
    parser.add_argument("--provenance", type=str, default=None, help="Filtra per fonte specifica (es. salesforces)")
    args = parser.parse_args()
    esegui_agente(limite=args.limite, provenance=args.provenance)