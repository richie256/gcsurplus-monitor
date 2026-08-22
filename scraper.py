#!/usr/bin/env python3
"""
GCSurplus Monitor — scrape gcsurplus.ca et notifie via Discord
quand de nouveaux articles correspondant aux critères configurés apparaissent.

Usage:
    python scraper.py                # lance la surveillance en boucle
    python scraper.py --once         # effectue une seule vérification
    python scraper.py --test-discord # envoie un message de test Discord
"""

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urljoin, parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────

CONFIG_FILE = Path(__file__).parent / "config.json"
SEEN_FILE   = Path(__file__).parent / "seen_items.json"
LOG_FILE    = Path(__file__).parent / "scraper.log"

BASE_URL    = "https://gcsurplus.ca"
SEARCH_URL  = f"{BASE_URL}/mn-fra.cfm"

DEFAULT_CONFIG = {
    "discord_webhook_url": "",
    "check_interval_minutes": 30,
    "searches": [
        {
            "keyword": "Montre",
            "category_code": "9800",
            "category_name": "9800 - Bijoux, pièces de collection, oeuvres d'art et artisanat, et plus",
            "enabled": True
        }
    ]
}

# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Dataclasses
# ─────────────────────────────────────────────

@dataclass
class Item:
    lot_number:    str
    sale_number:   str
    sale_ref:      str        # ex: "R6TO0018662 - 6TO016165-EP976-JG"
    title:         str
    description:   str        # description complète
    current_bid:   str
    min_bid:       str
    close_date:    str
    time_left:     str
    location:      str
    quantity:      str
    sale_type:     str
    condition:     str
    image_url:     str        # URL absolue de la 1re image
    all_image_urls: list
    url:           str
    found_at:      str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SearchConfig:
    keyword:       str
    category_code: str
    category_name: str
    enabled:       bool = True

# ─────────────────────────────────────────────
#  Config / state helpers
# ─────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        log.info("config.json introuvable — création avec les valeurs par défaut.")
        save_json(CONFIG_FILE, DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    return load_json(CONFIG_FILE)


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    data = load_json(SEEN_FILE)
    return set(data.get("seen", []))


def save_seen(seen: set) -> None:
    save_json(SEEN_FILE, {"seen": sorted(seen)})

# ─────────────────────────────────────────────
#  Scraping — page de liste
# ─────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
}


def build_search_url(category: str, keyword: str, start: int = 1) -> str:
    params = {
        "snc":      "wfsav",
        "vndsld":   "0",
        "sc":       "ach-shop",
        "lci":      "",
        "sf":       "ferm-clos",
        "so":       "ASC",
        "saleType": "A",
        "srchtype": "",
        "hpcs":     category,
        "hpsr":     "",
        "kws":      keyword,
        "jstp":     "sly",
        "str":      str(start),
        "sr":       "1",
    }
    return f"{SEARCH_URL}?{urlencode(params)}"


def parse_listing(html: str, keyword: str) -> list:
    """Extrait les références (lot, sale, url) depuis la page de liste."""
    soup = BeautifulSoup(html, "html.parser")
    refs = []
    seen_lots = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if "lcn=" not in href or "scn=" not in href:
            continue

        text = link.get_text(strip=True)
        if text.isdigit() or not text:
            continue

        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        lot  = qs.get("lcn", [""])[0]
        sale = qs.get("scn", [""])[0]

        if not lot or lot in seen_lots:
            continue
        seen_lots.add(lot)

        # Filtre par mot-clé (insensible à la casse)
        if keyword and keyword.lower() not in text.lower():
            continue

        refs.append({
            "lot":   lot,
            "sale":  sale,
            "title": text,
            "url":   urljoin(BASE_URL, href),
        })

    return refs


def has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return bool(soup.find("a", string=lambda t: t and "Suivant" in t))


def scrape_listing(category: str, keyword: str, session: requests.Session) -> list:
    """Parcourt toutes les pages de résultats et retourne les références."""
    all_refs = []
    start = 1
    max_pages = 20

    for page in range(max_pages):
        url = build_search_url(category, keyword, start)
        log.debug("Listing page %d: %s", page + 1, url)

        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.error("Erreur HTTP (page %d): %s", page + 1, e)
            break

        html = resp.text
        refs = parse_listing(html, keyword)
        all_refs.extend(refs)
        log.debug("Page %d → %d référence(s)", page + 1, len(refs))

        if not has_next_page(html) or not refs:
            break

        soup = BeautifulSoup(html, "html.parser")
        next_link = soup.find("a", string=lambda t: t and "Suivant" in t)
        if next_link:
            qs = parse_qs(urlparse(next_link["href"]).query)
            start = int(qs.get("str", [str(start + 10)])[0])
        else:
            break

        time.sleep(2)

    return all_refs

# ─────────────────────────────────────────────
#  Scraping — page de détail
# ─────────────────────────────────────────────

def _text_after(soup, label: str, default: str = "N/D") -> str:
    """Cherche un label dans la page et retourne le texte suivant."""
    # Cherche dans tous les textes
    full_text = soup.get_text(separator="\n")
    pattern = rf"{re.escape(label)}\s*[:\-]?\s*\n?(.*?)(?:\n|$)"
    m = re.search(pattern, full_text, re.IGNORECASE)
    if m:
        val = m.group(1).strip()
        if val:
            return val[:120]
    return default


def fetch_item_detail(ref: dict, session: requests.Session) -> Item:
    """Visite la page de détail d'un article et en extrait toutes les infos."""
    try:
        resp = session.get(ref["url"], headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("Impossible de charger la page détail pour lot %s: %s", ref["lot"], e)
        return _minimal_item(ref)

    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.find("main") or soup

    # ── Images ──────────────────────────────
    img_tags = main.find_all("img", class_="newViewer")
    image_urls = []
    for img in img_tags:
        src = img.get("src", "")
        if src:
            abs_src = urljoin(BASE_URL, src)
            image_urls.append(abs_src)

    first_image = image_urls[0] if image_urls else ""

    # ── Texte brut du contenu principal ────
    raw = main.get_text(separator="\n", strip=True)

    # ── Helpers d'extraction ────────────────
    def grab(labels, default="N/D"):
        for label in labels:
            for line in raw.splitlines():
                if label.lower() in line.lower():
                    # Retourne la ligne suivante non vide
                    idx = raw.splitlines().index(line)
                    for nxt in raw.splitlines()[idx+1:idx+4]:
                        nxt = nxt.strip()
                        if nxt and nxt not in (":", "-"):
                            return nxt[:120]
        return default

    def grab_inline(labels, default="N/D"):
        """Extrait valeur sur la même ligne ou la suivante."""
        for label in labels:
            m = re.search(
                rf"{re.escape(label)}\s*[:\-]?\s*([^\n]+)",
                raw, re.IGNORECASE
            )
            if m:
                val = m.group(1).strip().strip(":")
                if val:
                    return val[:120]
        return default

    # ── Champs ──────────────────────────────
    title        = grab_inline(["Article :"], ref["title"]) or ref["title"]
    current_bid  = grab_inline(["Soumission courante", "Montant des achats"], "N/D")
    min_bid      = grab_inline(["Enchère min", "Soumission minimale", "Prochaine soumission minimale"], "N/D")
    close_date   = grab_inline(["Date de clôture :"], "N/D")
    time_left    = grab_inline(["Restant :"], "N/D")
    location     = grab_inline(["Emplacement  :", "Emplacement :"], "N/D")
    quantity     = grab_inline(["Quantité :"], "N/D")
    sale_ref     = grab_inline(["Vente / Lot  :", "Vente / Lot :"], "N/D")
    condition    = grab_inline(["État :"], "N/D")

    # Type de vente depuis le titre de page ou le bouton
    page_text = soup.get_text().lower()
    if "acheter maintenant" in page_text:
        sale_type = "Acheter maintenant 🛒"
    elif "soumission ouverte" in page_text or "enchère ouverte" in page_text:
        sale_type = "Enchère ouverte 🔨"
    else:
        sale_type = "Vente 💼"

    # Description : bloc après "Description :"
    desc_match = re.search(r"Description\s*:\s*\n(.*?)(?:\nÉtat\s*:|\nCommentaires|\nInspection|\Z)",
                           raw, re.DOTALL | re.IGNORECASE)
    description = ""
    if desc_match:
        description = desc_match.group(1).strip()[:800]

    return Item(
        lot_number    = ref["lot"],
        sale_number   = ref["sale"],
        sale_ref      = sale_ref,
        title         = title,
        description   = description,
        current_bid   = current_bid,
        min_bid       = min_bid,
        close_date    = close_date,
        time_left     = time_left,
        location      = location,
        quantity      = quantity,
        sale_type     = sale_type,
        condition     = condition,
        image_url     = first_image,
        all_image_urls= image_urls,
        url           = ref["url"],
    )


def _minimal_item(ref: dict) -> Item:
    """Article minimal si la page détail est inaccessible."""
    return Item(
        lot_number    = ref["lot"],
        sale_number   = ref["sale"],
        sale_ref      = "N/D",
        title         = ref["title"],
        description   = "",
        current_bid   = "N/D",
        min_bid       = "N/D",
        close_date    = "N/D",
        time_left     = "N/D",
        location      = "N/D",
        quantity      = "N/D",
        sale_type     = "N/D",
        condition     = "N/D",
        image_url     = "",
        all_image_urls= [],
        url           = ref["url"],
    )

# ─────────────────────────────────────────────
#  Discord — embed riche avec image
# ─────────────────────────────────────────────

# Palette de couleurs par type de vente
COLORS = {
    "Enchère ouverte 🔨":    0xFEE75C,   # jaune ambré
    "Acheter maintenant 🛒": 0x57F287,   # vert émeraude
    "Soumission fermée 🔒":  0xED4245,   # rouge
    "Vente 💼":              0x5865F2,   # violet Discord
}


def build_embed(item: Item, search: SearchConfig) -> dict:
    """Construit un embed Discord riche avec image grande et métadonnées."""
    color = COLORS.get(item.sale_type, 0x5865F2)

    # Titre tronqué à 256 chars (limite Discord)
    title = f"🆕  {item.title}"[:256]

    # Description de l'embed (intro)
    embed_desc_parts = [
        f"📂 **{search.category_name}**",
        f"🔑 Mot-clé : `{search.keyword}`",
    ]
    if item.description:
        # Tronque proprement la description produit
        short_desc = item.description.replace("\n", " ").strip()
        if len(short_desc) > 300:
            short_desc = short_desc[:297] + "…"
        embed_desc_parts.append(f"\n> {short_desc}")

    embed_description = "\n".join(embed_desc_parts)

    # Champs de métadonnées
    fields = []

    if item.current_bid and item.current_bid != "N/D":
        fields.append({"name": "💰 Mise actuelle",    "value": f"**{item.current_bid}**", "inline": True})
    if item.min_bid and item.min_bid != "N/D":
        fields.append({"name": "📈 Prochaine mise min.", "value": item.min_bid,             "inline": True})

    fields.append({"name": "\u200b", "value": "\u200b", "inline": False})  # séparateur

    if item.close_date and item.close_date != "N/D":
        fields.append({"name": "📅 Date de clôture", "value": item.close_date,  "inline": True})
    if item.time_left and item.time_left != "N/D":
        fields.append({"name": "⏳ Temps restant",   "value": item.time_left,   "inline": True})

    fields.append({"name": "\u200b", "value": "\u200b", "inline": False})  # séparateur

    if item.location and item.location != "N/D":
        fields.append({"name": "📍 Emplacement",  "value": item.location,   "inline": True})
    if item.quantity and item.quantity != "N/D":
        fields.append({"name": "📦 Quantité",     "value": item.quantity,   "inline": True})

    fields.append({"name": "🏷️ Type de vente", "value": item.sale_type, "inline": True})

    if item.sale_ref and item.sale_ref != "N/D":
        fields.append({"name": "🔢 Réf. Vente / Lot", "value": f"`{item.sale_ref}`", "inline": False})

    if item.condition and item.condition != "N/D":
        cond_short = item.condition[:200]
        fields.append({"name": "🔍 État", "value": cond_short, "inline": False})

    # Nombre de photos disponibles
    n_photos = len(item.all_image_urls)
    if n_photos > 1:
        fields.append({
            "name": "📷 Photos",
            "value": f"{n_photos} photo(s) disponible(s) sur le site",
            "inline": True
        })

    embed = {
        "title":       title,
        "description": embed_description,
        "url":         item.url,
        "color":       color,
        "fields":      fields,
        "footer": {
            "text": f"GCSurplus Monitor  •  Lot {item.lot_number}  •  {item.found_at[:19].replace('T', ' ')}",
            "icon_url": "https://gcsurplus.ca/assets/favicon.ico",
        },
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    # Image principale en grand (image=) — Discord l'affiche pleine largeur
    if item.image_url:
        embed["image"] = {"url": item.image_url}

    return embed


def send_discord_notification(webhook_url: str, item: Item, search: SearchConfig) -> bool:
    """Envoie une notification Discord via webhook."""
    if not webhook_url:
        log.warning("Webhook Discord non configuré — notification ignorée.")
        return False

    embed = build_embed(item, search)

    payload = {
        "username":   "GCSurplus Monitor 🛒",
        "avatar_url": "https://gcsurplus.ca/images/gcsurplus-mini-logo-new.png",
        "embeds":     [embed],
    }

    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        log.info("✅ Discord notifié — lot %s.", item.lot_number)
        return True
    except requests.RequestException as e:
        log.error("Échec envoi Discord (lot %s): %s", item.lot_number, e)
        if hasattr(e, "response") and e.response is not None:
            log.error("Réponse Discord: %s", e.response.text[:300])
        return False


def send_discord_test(webhook_url: str) -> None:
    """Envoie un message de test avec un article fictif mais réaliste."""
    fake_item = Item(
        lot_number    = "762279",
        sale_number   = "601279",
        sale_ref      = "R6TO0018662 - 6TO016165-EP976-JG",
        title         = "Montre en or de 18 ct et en acier inoxydable de 26 mm Rolex 69173 Lady-Datejust (TEST)",
        description   = (
            "Marque : Rolex\n"
            "Numéro de modèle : 68173\n"
            "Numéro de série : L721270\n"
            "Poids : 55,15 g\n"
            "Type : pour femmes\n"
            "Mouvement : automatique\n"
            "Matériaux : acier inoxydable et or de 18 ct\n"
            "Taille du boîtier : 26 mm"
        ),
        current_bid   = "$6,200.00",
        min_bid       = "$6,300.00",
        close_date    = "25-août-2026 @ 09h00",
        time_left     = "3 jours 9 heures 30 minutes",
        location      = "North York, ON",
        quantity      = "1 (chaque)",
        sale_type     = "Enchère ouverte 🔨",
        condition     = "La montre est fonctionnelle. Égratignures légères.",
        image_url     = "https://gcsurplus.ca/lotImages/2988960.jpeg",
        all_image_urls= [
            "https://gcsurplus.ca/lotImages/2988960.jpeg",
            "https://gcsurplus.ca/lotImages/2988961.jpeg",
        ],
        url = (
            "https://gcsurplus.ca/mn-fra.cfm?snc=wfsav&sc=enc-bid"
            "&scn=601279&lcn=762279&lct=L"
        ),
    )
    fake_search = SearchConfig(
        keyword       = "Montre",
        category_code = "9800",
        category_name = "9800 - Bijoux, pièces de collection, oeuvres d'art et artisanat, et plus",
    )
    send_discord_notification(webhook_url, fake_item, fake_search)

# ─────────────────────────────────────────────
#  Boucle principale
# ─────────────────────────────────────────────

def run_once(config: dict, session: requests.Session) -> int:
    webhook_url = config.get("discord_webhook_url", "")
    seen        = load_seen()
    new_count   = 0

    searches = [
        SearchConfig(**s) for s in config.get("searches", [])
        if s.get("enabled", True)
    ]

    if not searches:
        log.warning("Aucune recherche activée dans config.json.")
        return 0

    for search in searches:
        log.info("🔍 mot-clé='%s'  catégorie='%s'", search.keyword, search.category_code)

        refs = scrape_listing(search.category_code, search.keyword, session)
        log.info("→ %d article(s) correspondant(s) trouvé(s).", len(refs))

        for ref in refs:
            unique_id = ref["lot"]
            if unique_id in seen:
                log.debug("Déjà vu : lot %s — ignoré.", unique_id)
                continue

            log.info("🆕 NOUVEAU lot %s : %s", ref["lot"], ref["title"][:80])

            # Récupère les détails complets + image
            item = fetch_item_detail(ref, session)
            seen.add(unique_id)
            new_count += 1

            if webhook_url:
                send_discord_notification(webhook_url, item, search)
                time.sleep(1)
            else:
                log.warning(
                    "Webhook Discord non configuré — ajoutez "
                    "'discord_webhook_url' dans config.json."
                )

            time.sleep(1)  # politesse entre les pages détail

    save_seen(seen)
    return new_count


def run_loop(config: dict) -> None:
    interval_min = config.get("check_interval_minutes", 30)
    log.info("🚀 Surveillance démarrée — vérification toutes les %d min.", interval_min)

    session = requests.Session()

    while True:
        # Skip checks between midnight (0) and 6 AM
        current_hour = datetime.now().hour
        if 0 <= current_hour < 6:
            log.info("😴 Heures creuses (00h-06h) — vérification suspendue.")
            log.info("⏳ Prochaine vérification à 6h00.")
            # Sleep until 6 AM
            time.sleep((6 - current_hour) * 3600)
            continue

        try:
            n = run_once(config, session)
            log.info("✓ Cycle terminé — %d nouvel(aux) article(s).", n)
        except Exception as e:
            log.exception("Erreur inattendue : %s", e)

        log.info("⏳ Prochain cycle dans %d minutes.", interval_min)
        time.sleep(interval_min * 60)

# ─────────────────────────────────────────────
#  Point d'entrée
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Moniteur GCSurplus avec notifications Discord"
    )
    parser.add_argument("--once",         action="store_true",
                        help="Effectue une seule vérification puis quitte")
    parser.add_argument("--test-discord", action="store_true",
                        help="Envoie un message de test Discord et quitte")
    args = parser.parse_args()

    config = load_config()

    if args.test_discord:
        webhook_url = config.get("discord_webhook_url", "")
        if not webhook_url:
            print("⚠️  Configurez 'discord_webhook_url' dans config.json avant de tester.")
            sys.exit(1)
        send_discord_test(webhook_url)
        print("✅ Message de test envoyé !")
        sys.exit(0)

    if args.once:
        session = requests.Session()
        n = run_once(config, session)
        print(f"✅ Vérification terminée — {n} nouvel(aux) article(s) détecté(s).")
        sys.exit(0)

    run_loop(config)


if __name__ == "__main__":
    main()
