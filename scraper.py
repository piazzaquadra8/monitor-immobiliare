"""
Monitor Mercato Immobiliare - Nord-Est Sardegna
Scrapa portali e siti agenzie, confronta con snapshot precedente,
invia report email settimanale.
"""

import json
import os
import re
import time
import smtplib
import hashlib
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─── CONFIGURAZIONE ────────────────────────────────────────────────────────────
PREZZO_MIN = 150000
GHOST_DAYS = 90  # annunci più vecchi = stock fantasma

ZONE = {
    "porto_rotondo": ["porto rotondo", "porto rotondo"],
    "porto_cervo":   ["porto cervo", "porto cervo"],
    "nord_est":      ["olbia", "arzachena", "san teodoro", "golfo aranci",
                      "palau", "santa teresa", "cannigione", "baja sardinia",
                      "costa smeralda", "poltu quatu"]
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SNAPSHOT_FILE = Path(__file__).parent / "data" / "listings_snapshot.json"
# ──────────────────────────────────────────────────────────────────────────────


def make_id(listing: dict) -> str:
    """ID univoco basato su fonte + URL o caratteristiche principali."""
    key = listing.get("url") or f"{listing['fonte']}_{listing.get('prezzo')}_{listing.get('mq')}_{listing.get('zona')}"
    return hashlib.md5(key.encode()).hexdigest()


def parse_prezzo(testo: str) -> int | None:
    """Estrae valore numerico dal testo prezzo."""
    nums = re.sub(r"[^\d]", "", testo)
    return int(nums) if nums else None


def scrape_immobiliareit() -> list[dict]:
    """Scrapa Immobiliare.it - Nord-Est Sardegna, 150k+"""
    results = []
    page = 1
    while page <= 5:  # max 5 pagine per run
        url = (
            f"https://www.immobiliare.it/vendita-case/nord-est-sardegna/"
            f"?prezzoMinimo={PREZZO_MIN}&pag={page}"
        )
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select("li[data-listing-id]")
            if not cards:
                break
            for card in cards:
                try:
                    prezzo_el = card.select_one("[class*='price']")
                    titolo_el = card.select_one("a[class*='title'], h2 a, h3 a")
                    zona_el   = card.select_one("[class*='location'], [class*='city']")
                    mq_el     = card.select_one("[aria-label='superficie'], [class*='surface']")
                    link      = card.select_one("a[href*='/annunci/']")

                    prezzo = parse_prezzo(prezzo_el.text) if prezzo_el else None
                    if prezzo and prezzo < PREZZO_MIN:
                        continue

                    listing = {
                        "fonte":      "immobiliare.it",
                        "agenzia":    None,
                        "titolo":     titolo_el.text.strip() if titolo_el else "",
                        "zona":       zona_el.text.strip().lower() if zona_el else "",
                        "prezzo":     prezzo,
                        "mq":         int(re.sub(r"\D", "", mq_el.text)) if mq_el and re.search(r"\d", mq_el.text) else None,
                        "url":        "https://www.immobiliare.it" + link["href"] if link and link.get("href", "").startswith("/") else (link["href"] if link else ""),
                        "data_rilevazione": date.today().isoformat(),
                    }
                    results.append(listing)
                except Exception:
                    continue
            time.sleep(2)
            page += 1
        except Exception as e:
            print(f"[immobiliare.it] Errore pagina {page}: {e}")
            break
    print(f"[immobiliare.it] {len(results)} annunci trovati")
    return results


def scrape_idealista() -> list[dict]:
    """Scrapa Idealista - Sardegna NE, 150k+"""
    results = []
    urls = [
        f"https://www.idealista.it/vendita-immobili/sardegna/olbia-tempio/?prezzo_min={PREZZO_MIN}",
        f"https://www.idealista.it/vendita-immobili/sardegna/olbia-tempio/municipio-olbia/?prezzo_min={PREZZO_MIN}",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            articles = soup.select("article.item")
            for art in articles:
                try:
                    prezzo_el = art.select_one(".item-price")
                    zona_el   = art.select_one(".item-detail-char .item-detail")
                    titolo_el = art.select_one("a.item-link")
                    mq_el     = art.select_one(".item-detail:nth-child(2)")

                    prezzo = parse_prezzo(prezzo_el.text) if prezzo_el else None
                    if prezzo and prezzo < PREZZO_MIN:
                        continue

                    listing = {
                        "fonte":      "idealista.it",
                        "agenzia":    None,
                        "titolo":     titolo_el.text.strip() if titolo_el else "",
                        "zona":       zona_el.text.strip().lower() if zona_el else "",
                        "prezzo":     prezzo,
                        "mq":         int(re.sub(r"\D", "", mq_el.text)) if mq_el and re.search(r"\d", mq_el.text) else None,
                        "url":        "https://www.idealista.it" + titolo_el["href"] if titolo_el and titolo_el.get("href", "").startswith("/") else "",
                        "data_rilevazione": date.today().isoformat(),
                    }
                    results.append(listing)
                except Exception:
                    continue
            time.sleep(3)
        except Exception as e:
            print(f"[idealista] Errore: {e}")
    print(f"[idealista] {len(results)} annunci trovati")
    return results


def scrape_agenzia(nome: str, url_base: str, selettori: dict) -> list[dict]:
    """Scraper generico per siti agenzie."""
    results = []
    try:
        r = requests.get(url_base, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select(selettori.get("card", "article, .property, .listing"))
        for card in cards:
            try:
                prezzo_el = card.select_one(selettori.get("prezzo", ".price, [class*='price']"))
                zona_el   = card.select_one(selettori.get("zona", ".location, [class*='location']"))
                titolo_el = card.select_one(selettori.get("titolo", "h2, h3, .title"))
                link_el   = card.select_one("a[href]")
                mq_el     = card.select_one(selettori.get("mq", "[class*='surface'], [class*='mq'], [class*='area']"))

                prezzo = parse_prezzo(prezzo_el.text) if prezzo_el else None
                if prezzo and prezzo < PREZZO_MIN:
                    continue

                href = link_el["href"] if link_el else ""
                if href and not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(url_base, href)

                listing = {
                    "fonte":      nome,
                    "agenzia":    nome,
                    "titolo":     titolo_el.text.strip() if titolo_el else "",
                    "zona":       zona_el.text.strip().lower() if zona_el else "",
                    "prezzo":     prezzo,
                    "mq":        int(re.sub(r"\D", "", mq_el.text)) if mq_el and re.search(r"\d", mq_el.text) else None,
                    "url":        href,
                    "data_rilevazione": date.today().isoformat(),
                }
                results.append(listing)
            except Exception:
                continue
    except Exception as e:
        print(f"[{nome}] Errore: {e}")
    print(f"[{nome}] {len(results)} annunci trovati")
    return results


def scrape_engel() -> list[dict]:
    return scrape_agenzia(
        "Engel & Völkers",
        "https://www.engelvoelkers.com/it-it/ricerca/?q=&startIndex=0&businessArea=residential&sortOrder=DESC&sortField=timestamp&pageSize=18&facets=sub_division_txt%3ASardegna%3Bcontract_type_txt%3Asell%3B",
        {
            "card":   ".ev-property-search-result",
            "prezzo": ".ev-property-search-result__price",
            "zona":   ".ev-property-search-result__address",
            "titolo": ".ev-property-search-result__title",
        }
    )


def scrape_immobilsarda() -> list[dict]:
    return scrape_agenzia(
        "Immobilsarda",
        "https://www.immobilsarda.it/it/immobili/?tipologia=vendita&prezzo_min=150000",
        {
            "card":   ".property-item, .listing-item, article",
            "prezzo": ".price, .prezzo",
            "zona":   ".location, .zona, .citta",
            "titolo": "h2, h3, .title",
        }
    )


def scrape_luxuryesmeralda() -> list[dict]:
    return scrape_agenzia(
        "Luxury Esmeralda",
        "https://www.luxuryesmeralda.com/it/immobili-vendita/",
        {
            "card":   ".property, .listing, article, .item",
            "prezzo": ".price, .prezzo, [class*='price']",
            "zona":   ".location, .zona, [class*='location']",
            "titolo": "h2, h3, .title, [class*='title']",
        }
    )


# ─── ANALISI ──────────────────────────────────────────────────────────────────

def classifica_zona(zona: str) -> str:
    """Classifica la zona: porto_rotondo, porto_cervo, nord_est, altro."""
    zona_lower = zona.lower()
    for key, keywords in ZONE.items():
        if any(kw in zona_lower for kw in keywords):
            return key
    return "altro"


def probabilita_vendita(listing: dict, giorni_online: int) -> dict:
    """
    Calcola la probabilità che un annuncio rimosso sia stato venduto
    (vs ritirato, errore, rilistato).

    Fattori:
    - Stagione: inverno sardo = mercato quasi fermo
    - Giorni online: <7gg = quasi certamente non vendita; 45-90gg = zona ottimale
    - Fascia di prezzo: >1M allungano i tempi

    Restituisce: { score: float 0-1, label, colore, motivo }
    """
    mese = date.today().month
    prezzo = listing.get("prezzo") or 0

    # 1. Stagionale (mercato sardo)
    if mese in (6, 7, 8, 9):
        s_score, s_nota = 0.85, "stagione alta"
    elif mese in (4, 5, 10):
        s_score, s_nota = 0.55, "stagione intermedia"
    elif mese in (3, 11):
        s_score, s_nota = 0.30, "stagione bassa"
    else:
        s_score, s_nota = 0.15, "mercato invernale quasi fermo"

    # 2. Giorni online
    if giorni_online < 7:
        g_score, g_nota = 0.10, f"solo {giorni_online}gg → sospetto ritiro/errore"
    elif giorni_online <= 20:
        g_score, g_nota = 0.35, f"{giorni_online}gg → veloce, possibile ma raro"
    elif giorni_online <= 60:
        g_score, g_nota = 0.85, f"{giorni_online}gg → tempi realistici per trattativa"
    elif giorni_online <= 90:
        g_score, g_nota = 0.70, f"{giorni_online}gg → nella norma"
    elif giorni_online <= 150:
        g_score, g_nota = 0.40, f"{giorni_online}gg → inizia ad essere lungo"
    else:
        g_score, g_nota = 0.15, f"{giorni_online}gg → molto probabilmente ritirato"

    # 3. Prezzo (moltiplicatore)
    if prezzo < 300_000:
        p_mult, p_nota = 1.15, "fascia accessibile (più liquida)"
    elif prezzo < 700_000:
        p_mult, p_nota = 1.00, "fascia medio-alta"
    elif prezzo < 1_500_000:
        p_mult, p_nota = 0.80, "fascia alta (pochi acquirenti)"
    elif prezzo < 3_000_000:
        p_mult, p_nota = 0.60, "fascia lusso (mercato ristretto)"
    else:
        p_mult, p_nota = 0.40, "ultra-lusso (richiede tempo)"

    score = round(max(0.0, min(1.0, (s_score * 0.50 + g_score * 0.50) * p_mult)), 2)

    if score >= 0.60:
        label, colore = "🟢 Probabile vendita", "#276749"
    elif score >= 0.35:
        label, colore = "🟡 Incerto", "#744210"
    else:
        label, colore = "🔴 Probabile ritiro", "#c53030"

    return {
        "score": score,
        "label": label,
        "colore": colore,
        "motivo": f"{s_nota} · {g_nota} · {p_nota}",
        "pct": f"{int(score*100)}%",
    }


def is_ghost(listing: dict, snapshot: dict) -> bool:
    """True se l'annuncio è nello snapshot da più di GHOST_DAYS giorni senza variazioni."""
    lid = make_id(listing)
    if lid not in snapshot:
        return False
    first_seen = snapshot[lid].get("first_seen")
    if not first_seen:
        return False
    delta = (date.today() - date.fromisoformat(first_seen)).days
    prezzo_cambiato = snapshot[lid].get("prezzo") != listing.get("prezzo")
    return delta > GHOST_DAYS and not prezzo_cambiato


def detect_duplicates(listings: list[dict]) -> set[str]:
    """Rileva duplicati: stesso prezzo ± 5%, stessa mq, zona simile, agenzia diversa."""
    duplicates = set()
    for i, a in enumerate(listings):
        for j, b in enumerate(listings):
            if i >= j:
                continue
            if not a.get("prezzo") or not b.get("prezzo"):
                continue
            if not a.get("mq") or not b.get("mq"):
                continue
            prezzo_simile = abs(a["prezzo"] - b["prezzo"]) / max(a["prezzo"], b["prezzo"]) < 0.05
            mq_simile = abs(a["mq"] - b["mq"]) <= 5
            zona_simile = classifica_zona(a["zona"]) == classifica_zona(b["zona"])
            agenzia_diversa = a.get("fonte") != b.get("fonte")
            if prezzo_simile and mq_simile and zona_simile and agenzia_diversa:
                duplicates.add(make_id(a))
                duplicates.add(make_id(b))
    return duplicates


def analizza(current: list[dict], snapshot: dict) -> dict:
    """Confronta listings correnti con snapshot. Restituisce analisi."""
    current_ids = {make_id(l): l for l in current}
    prev_ids = set(snapshot.keys())

    nuovi     = [l for lid, l in current_ids.items() if lid not in prev_ids]
    rimossi   = [v for lid, v in snapshot.items() if lid not in current_ids]
    variazioni_prezzo = []

    for lid, l in current_ids.items():
        if lid in snapshot and snapshot[lid].get("prezzo") != l.get("prezzo"):
            old_p = snapshot[lid].get("prezzo")
            new_p = l.get("prezzo")
            if old_p and new_p:
                variazioni_prezzo.append({
                    **l,
                    "prezzo_old": old_p,
                    "prezzo_new": new_p,
                    "delta_pct": round((new_p - old_p) / old_p * 100, 1)
                })

    ghost_ids   = {make_id(l) for l in current if is_ghost(l, snapshot)}
    duplic_ids  = detect_duplicates(current)

    # Arricchisci rimossi con probabilità vendita
    rimossi_arricchiti = []
    for v in rimossi:
        giorni = (date.today() - date.fromisoformat(v["first_seen"])).days if v.get("first_seen") else 45
        prob = probabilita_vendita(v, giorni)
        rimossi_arricchiti.append({**v, "giorni_online": giorni, "prob_vendita": prob})
    rimossi = rimossi_arricchiti

    # Vendite probabili = score >= 0.60
    vendite_rapide = [v for v in rimossi if v["prob_vendita"]["score"] >= 0.60]

    # Suddivisione per zona
    def per_zona(listings):
        out = {"porto_rotondo": [], "porto_cervo": [], "nord_est": [], "altro": []}
        for l in listings:
            out[classifica_zona(l.get("zona", ""))].append(l)
        return out

    # Prezzo medio per zona (annunci reali = non ghost, non duplicati)
    reali = [l for l in current if make_id(l) not in ghost_ids and make_id(l) not in duplic_ids]
    prezzi_per_zona = {}
    for key in ["porto_rotondo", "porto_cervo", "nord_est"]:
        zona_listings = [l for l in reali if classifica_zona(l.get("zona", "")) == key and l.get("prezzo")]
        if zona_listings:
            prezzi_per_zona[key] = {
                "media": int(sum(l["prezzo"] for l in zona_listings) / len(zona_listings)),
                "min":   min(l["prezzo"] for l in zona_listings),
                "max":   max(l["prezzo"] for l in zona_listings),
                "count": len(zona_listings),
            }

    return {
        "data": date.today().isoformat(),
        "totale_annunci": len(current),
        "annunci_reali": len(reali),
        "ghost_count": len(ghost_ids),
        "duplicati_count": len(duplic_ids),
        "nuovi": per_zona(nuovi),
        "rimossi": per_zona(rimossi),
        "variazioni_prezzo": variazioni_prezzo,
        "vendite_rapide": vendite_rapide,
        "prezzi_per_zona": prezzi_per_zona,
    }


# ─── SNAPSHOT ─────────────────────────────────────────────────────────────────

def carica_snapshot() -> dict:
    if SNAPSHOT_FILE.exists():
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    return {}


def aggiorna_snapshot(current: list[dict], snapshot: dict) -> dict:
    new_snapshot = {}
    today = date.today().isoformat()
    for l in current:
        lid = make_id(l)
        entry = {**l}
        entry["first_seen"] = snapshot.get(lid, {}).get("first_seen", today)
        new_snapshot[lid] = entry
    return new_snapshot


def salva_snapshot(snapshot: dict):
    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


# ─── EMAIL ────────────────────────────────────────────────────────────────────

def fmt_prezzo(p) -> str:
    if not p:
        return "N/D"
    return f"€ {p:,.0f}".replace(",", ".")


def zona_label(key: str) -> str:
    return {"porto_rotondo": "Porto Rotondo", "porto_cervo": "Porto Cervo",
            "nord_est": "Nord-Est Sardegna", "altro": "Altra zona"}.get(key, key)


def genera_analisi_claude(analisi: dict) -> str:
    """Chiama l'API di Claude per generare l'analisi narrativa del report."""
    import json as _json

    nuovi_count   = sum(len(v) for v in analisi["nuovi"].values())
    rimossi_count = sum(len(v) for v in analisi["rimossi"].values())
    vendite_prob  = len(analisi["vendite_rapide"])

    # Prepara un riassunto compatto dei dati da passare a Claude
    prompt = f"""Sei un esperto del mercato immobiliare della Costa Smeralda e del Nord-Est Sardegna.
Analizza i seguenti dati raccolti questa settimana e scrivi una "Lettura della settimana" in italiano,
concisa e diretta, come la scriverebbe un analista esperto che parla a un agente immobiliare locale.

DATI SETTIMANA:
- Data: {analisi['data']}
- Annunci totali rilevati: {analisi['totale_annunci']}
- Annunci reali (no ghost, no duplicati): {analisi['annunci_reali']}
- Stock fantasma (>90gg immobili): {analisi['ghost_count']}
- Probabili duplicati: {analisi['duplicati_count']}
- Nuovi annunci questa settimana: {nuovi_count}
- Rimossi questa settimana: {rimossi_count}
- Di cui probabili vendite reali (score >60%): {vendite_prob}

PREZZI PER ZONA (annunci reali):
{_json.dumps(analisi['prezzi_per_zona'], ensure_ascii=False, indent=2)}

VARIAZIONI DI PREZZO:
{_json.dumps([{
    'zona': classifica_zona(v.get('zona','')),
    'prezzo_old': v['prezzo_old'],
    'prezzo_new': v['prezzo_new'],
    'delta_pct': v['delta_pct']
} for v in analisi['variazioni_prezzo']], ensure_ascii=False, indent=2)}

Rispondi con 4-5 punti in HTML usando tag <li>. Ogni punto deve essere concreto e utile.
L'ultimo punto deve rispondere alla domanda: "se non ricevo richieste, è colpa mia o del mercato?"
Non usare tag <ul>, solo i <li>. Non aggiungere nient'altro oltre ai tag <li>."""

    try:
        import anthropic
        client = anthropic.Anthropic()  # legge ANTHROPIC_API_KEY da os.environ
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"[Claude API] Errore: {e}")
        return f"<li>Analisi AI non disponibile questa settimana ({e}).</li>"


def build_html(analisi: dict) -> str:
    data = analisi["data"]
    totale = analisi["totale_annunci"]
    reali = analisi["annunci_reali"]
    ghost = analisi["ghost_count"]
    duplic = analisi["duplicati_count"]

    def tabella_zona(listings_per_zona: dict, label: str) -> str:
        rows = ""
        for zona in ["porto_rotondo", "porto_cervo", "nord_est", "altro"]:
            items = listings_per_zona.get(zona, [])
            if not items:
                continue
            for l in items[:10]:  # max 10 per zona
                rows += f"""
                <tr>
                  <td>{zona_label(zona)}</td>
                  <td>{l.get('titolo', '')[:50]}</td>
                  <td>{l.get('fonte','')}</td>
                  <td>{fmt_prezzo(l.get('prezzo'))}</td>
                  <td>{l.get('mq') or 'N/D'} mq</td>
                </tr>"""
        if not rows:
            return ""
        return f"""
        <h3 style="color:#2c5282;margin-top:24px">{label}</h3>
        <table style="border-collapse:collapse;width:100%;font-size:13px">
          <thead>
            <tr style="background:#ebf4ff">
              <th style="padding:6px 10px;text-align:left">Zona</th>
              <th style="padding:6px 10px;text-align:left">Titolo</th>
              <th style="padding:6px 10px;text-align:left">Fonte</th>
              <th style="padding:6px 10px;text-align:right">Prezzo</th>
              <th style="padding:6px 10px;text-align:right">Mq</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    # Confronto zone
    confronto = ""
    for zona in ["porto_rotondo", "porto_cervo"]:
        dati = analisi["prezzi_per_zona"].get(zona)
        if dati:
            confronto += f"""
            <tr>
              <td style="padding:6px 10px;font-weight:bold">{zona_label(zona)}</td>
              <td style="padding:6px 10px;text-align:right">{dati['count']}</td>
              <td style="padding:6px 10px;text-align:right">{fmt_prezzo(dati['media'])}</td>
              <td style="padding:6px 10px;text-align:right">{fmt_prezzo(dati['min'])}</td>
              <td style="padding:6px 10px;text-align:right">{fmt_prezzo(dati['max'])}</td>
            </tr>"""

    # Variazioni prezzo
    var_rows = ""
    for v in analisi["variazioni_prezzo"][:15]:
        colore = "#c53030" if v["delta_pct"] < 0 else "#276749"
        segno = "↓" if v["delta_pct"] < 0 else "↑"
        var_rows += f"""
        <tr>
          <td>{zona_label(classifica_zona(v.get('zona','')))}</td>
          <td>{v.get('titolo','')[:40]}</td>
          <td>{v.get('fonte','')}</td>
          <td style="text-align:right">{fmt_prezzo(v['prezzo_old'])}</td>
          <td style="text-align:right">{fmt_prezzo(v['prezzo_new'])}</td>
          <td style="text-align:right;color:{colore};font-weight:bold">{segno} {abs(v['delta_pct'])}%</td>
        </tr>"""

    vendite_rapide_count = len(analisi["vendite_rapide"])
    rimossi_count = sum(len(v) for v in analisi["rimossi"].values())

    # Analisi narrativa Claude API
    analisi_ai = genera_analisi_claude(analisi)

    # Segnale mercato
    if vendite_rapide_count >= 5:
        segnale = "🟢 Mercato attivo — buona rotazione (<30gg)"
    elif vendite_rapide_count >= 2:
        segnale = "🟡 Mercato tiepido — qualche vendita rapida"
    else:
        segnale = "🔴 Mercato lento — poca rotazione"

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#1a202c">
  
  <div style="background:#2c5282;color:white;padding:20px;border-radius:8px 8px 0 0">
    <h1 style="margin:0;font-size:22px">🏠 Report Mercato Immobiliare</h1>
    <p style="margin:6px 0 0;opacity:0.8">Nord-Est Sardegna · Settimana del {data}</p>
  </div>

  <div style="background:#f7fafc;padding:20px;border:1px solid #e2e8f0;border-top:none">
    
    <!-- SEGNALE MERCATO -->
    <div style="background:white;border:1px solid #e2e8f0;border-radius:6px;padding:16px;margin-bottom:20px">
      <h2 style="margin:0 0 12px;font-size:16px;color:#2d3748">📊 Segnale Mercato Settimana</h2>
      <p style="font-size:18px;margin:0;font-weight:bold">{segnale}</p>
      <p style="color:#718096;font-size:13px;margin:8px 0 0">
        Basato su: {vendite_rapide_count} vendite rapide (&lt;30gg) · {rimossi_count} annunci rimossi totali
      </p>
    </div>

    <!-- KPI PRINCIPALI -->
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
      {_kpi("Annunci totali", totale, "")}
      {_kpi("Annunci reali", reali, "👍")}
      {_kpi("Stock fantasma", ghost, "👻")}
      {_kpi("Probabili duplicati", duplic, "⚠️")}
    </div>

    <!-- CONFRONTO PR vs PC -->
    <div style="background:white;border:1px solid #e2e8f0;border-radius:6px;padding:16px;margin-bottom:20px">
      <h2 style="margin:0 0 12px;font-size:16px;color:#2d3748">⚖️ Porto Rotondo vs Porto Cervo</h2>
      <table style="border-collapse:collapse;width:100%;font-size:13px">
        <thead>
          <tr style="background:#ebf4ff">
            <th style="padding:6px 10px;text-align:left">Zona</th>
            <th style="padding:6px 10px;text-align:right">Annunci reali</th>
            <th style="padding:6px 10px;text-align:right">Prezzo medio</th>
            <th style="padding:6px 10px;text-align:right">Min</th>
            <th style="padding:6px 10px;text-align:right">Max</th>
          </tr>
        </thead>
        <tbody>{confronto or "<tr><td colspan='5' style='padding:10px;color:#718096'>Dati non ancora disponibili</td></tr>"}</tbody>
      </table>
    </div>

    <!-- NUOVI ANNUNCI -->
    {tabella_zona(analisi["nuovi"], "🆕 Nuovi annunci questa settimana")}

    <!-- RIMOSSI (proxy vendita) -->
    {tabella_zona(analisi["rimossi"], "✅ Rimossi dal mercato (proxy vendita/ritiro)")}

    <!-- VARIAZIONI PREZZO -->

    <h3 style="color:#2c5282;margin-top:24px">💰 Variazioni di prezzo</h3>
    <table style="border-collapse:collapse;width:100%;font-size:13px">
      <thead>
        <tr style="background:#ebf4ff">
          <th style="padding:6px 10px;text-align:left">Zona</th>
          <th style="padding:6px 10px;text-align:left">Titolo</th>
          <th style="padding:6px 10px;text-align:left">Fonte</th>
          <th style="padding:6px 10px;text-align:right">Vecchio</th>
          <th style="padding:6px 10px;text-align:right">Nuovo</th>
          <th style="padding:6px 10px;text-align:right">Delta</th>
        </tr>
      </thead>
      <tbody>{var_rows}</tbody>
    </table>'''}

    <!-- ANALISI AI -->
    <div style="background:#fffbeb;border:1px solid #f6e05e;border-radius:6px;padding:18px;margin-top:24px">
      <h3 style="margin:0 0 12px;font-size:14px;color:#744210">🧠 Lettura della settimana</h3>
      <ul style="margin:0;padding-left:18px;font-size:13px;color:#744210;line-height:2.0">
        {analisi_ai}
      </ul>
    </div>

    <hr style="margin:24px 0;border:none;border-top:1px solid #e2e8f0">
    <p style="color:#a0aec0;font-size:11px;margin:0">
      Report generato automaticamente · Dati da Immobiliare.it, Idealista, Engel &amp; Völkers, Immobilsarda, Luxury Esmeralda<br>
      Analisi narrativa generata da Claude AI · Stock fantasma = annunci online &gt;{GHOST_DAYS}gg senza variazioni · Duplicati = stesso immobile su più fonti
    </p>
  </div>
</body>
</html>"""
    return html


def _kpi(label: str, value, icon: str) -> str:
    return f"""
    <div style="background:white;border:1px solid #e2e8f0;border-radius:6px;padding:14px;text-align:center">
      <div style="font-size:22px;font-weight:bold;color:#2c5282">{icon} {value}</div>
      <div style="font-size:11px;color:#718096;margin-top:4px">{label}</div>
    </div>"""


def invia_email(html: str, analisi: dict):
    sender    = os.environ["GMAIL_SENDER"]
    password  = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ["EMAIL_RECIPIENT"]

    nuovi_count = sum(len(v) for v in analisi["nuovi"].values())
    rimossi_count = sum(len(v) for v in analisi["rimossi"].values())
    subject = f"📊 Mercato NE Sardegna · {analisi['data']} · +{nuovi_count} nuovi · -{rimossi_count} rimossi"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, recipient, msg.as_string())
    print(f"✅ Email inviata a {recipient}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"=== Monitor avviato: {datetime.now()} ===")

    # Scraping di tutte le fonti
    all_listings = []
    for fn in [scrape_immobiliareit, scrape_idealista,
               scrape_engel, scrape_immobilsarda, scrape_luxuryesmeralda]:
        try:
            results = fn()
            all_listings.extend(results)
        except Exception as e:
            print(f"Fonte fallita: {fn.__name__}: {e}")
        time.sleep(2)

    print(f"\nTotale listings raccolti: {len(all_listings)}")

    # Carica snapshot precedente
    snapshot = carica_snapshot()
    print(f"Snapshot precedente: {len(snapshot)} annunci")

    # Analisi
    analisi = analizza(all_listings, snapshot)
    print(f"Nuovi: {sum(len(v) for v in analisi['nuovi'].values())}")
    print(f"Rimossi: {sum(len(v) for v in analisi['rimossi'].values())}")
    print(f"Ghost: {analisi['ghost_count']}")

    # Aggiorna e salva snapshot
    new_snapshot = aggiorna_snapshot(all_listings, snapshot)
    salva_snapshot(new_snapshot)
    print("Snapshot aggiornato e salvato")

    # Invia email
    html = build_html(analisi)
    invia_email(html, analisi)

    print("=== Monitor completato ===")


if __name__ == "__main__":
    main()
