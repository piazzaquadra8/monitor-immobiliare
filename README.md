# 🏠 Monitor Mercato Immobiliare — Setup

## Cosa fa
Ogni lunedì mattina analizza automaticamente il mercato immobiliare del Nord-Est Sardegna
(150k+) e ti manda una email con:

- Nuovi annunci della settimana per zona
- Annunci rimossi (proxy di vendita/ritiro)
- Variazioni di prezzo
- Confronto Porto Rotondo vs Porto Cervo
- Identificazione stock fantasma (>90gg immobili) e duplicati

Fonti: Immobiliare.it · Idealista · Engel & Völkers · Immobilsarda · Luxury Esmeralda

---

## Setup (una volta sola, ~20 minuti)

### STEP 1 — Crea il repository GitHub

1. Vai su [github.com](https://github.com) e crea un account se non ce l'hai
2. Clicca **New repository**
3. Nome: `monitor-immobiliare` (o quello che vuoi)
4. Spunta **Private** (i tuoi dati non li vede nessuno)
5. Clicca **Create repository**
6. Carica tutti i file di questa cartella nel repo
   (trascina i file nella pagina del repo, o usa GitHub Desktop)

### STEP 2 — Crea un Gmail dedicato per l'invio

> Consiglio: crea un indirizzo tipo `monitor.immobiliare.tuonome@gmail.com`
> Serve solo per mandare le email, non devi usarlo per altro.

1. Crea il nuovo account Gmail
2. Vai su [myaccount.google.com/security](https://myaccount.google.com/security)
3. Attiva la **verifica in due passaggi** (obbligatorio per il passo successivo)
4. Cerca **"Password per le app"** nella barra di ricerca delle impostazioni Google
5. Crea una nuova password per app: nome → `monitor-immobiliare`
6. **Copia la password di 16 caratteri** che ti mostra (tipo: `abcd efgh ijkl mnop`)

### STEP 3 — Aggiungi i Secrets su GitHub

I Secrets sono come variabili d'ambiente segrete: GitHub Actions le usa
ma non le mostra a nessuno, neanche nei log.

1. Nel tuo repository GitHub, vai su **Settings → Secrets and variables → Actions**
2. Clicca **New repository secret** per ognuno di questi tre:

| Nome secret        | Valore                                  |
|--------------------|-----------------------------------------|
| `GMAIL_SENDER`     | l'email del mittente (il Gmail nuovo)   |
| `GMAIL_APP_PASSWORD` | la password 16 caratteri dello step 2 |
| `EMAIL_RECIPIENT`  | la tua email dove vuoi ricevere i report |

### STEP 4 — Primo test manuale

1. Nel repo GitHub, vai su **Actions**
2. Clicca su **Monitor Mercato Immobiliare** nella lista a sinistra
3. Clicca **Run workflow** → **Run workflow** (pulsante verde)
4. Aspetta 2-3 minuti
5. Se tutto va bene: ricevi l'email e vedi una ✅ verde nell'Actions log

### STEP 5 — Da questo momento è automatico

Ogni lunedì mattina alle 7:00 ora italiana riceverai il report.
Non devi fare nulla.

---

## Risoluzione problemi

**L'Actions si completa ma non ricevo l'email**
→ Controlla che `EMAIL_RECIPIENT` sia scritto correttamente nei Secrets
→ Controlla la cartella spam

**L'Actions fallisce con errore rosso**
→ Clicca sul job fallito → leggi l'output → cerca la riga con "Error"
→ Quasi sempre è una credenziale sbagliata nei Secrets

**Voglio ricevere il report anche il venerdì**
→ Modifica `.github/workflows/monitor.yml`, riga `cron`:
→ Cambia `'0 6 * * 1'` in `'0 6 * * 1,5'`

**Voglio cambiare la fascia di prezzo**
→ Apri `scraper.py`, riga `PREZZO_MIN = 150000`
→ Cambia il valore e salva

---

## Note tecniche
- Lo snapshot (storico annunci) viene salvato automaticamente in `data/listings_snapshot.json`
- Il confronto settimana-su-settimana funziona dal **secondo run** in poi
- Il primo run stabilisce la baseline
- I siti delle agenzie possono cambiare la struttura HTML: se una fonte smette di funzionare,
  le altre continuano normalmente
