# GCSurplus Monitor 🛒

Surveille le site [GCSurplus](https://gcsurplus.ca) et envoie des notifications Discord
lorsque de nouveaux articles correspondant à vos critères apparaissent.

## Fonctionnalités

- 🔍 Recherche par **mot-clé** dans une **catégorie** spécifique
- 🔔 Notifications Discord avec **embeds riches** (couleur, prix, date de clôture, etc.)
- 💾 Mémorisation des articles déjà vus (pas de doublon)
- ⚙️ Configuration entièrement **configurable via `config.json`**
- 📄 Logs persistants dans `scraper.log`
- 🐳 Support Docker avec configuration de fuseau horaire

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Éditez `config.json` :

```json
{
  "discord_webhook_url": "https://discord.com/api/webhooks/VOTRE_WEBHOOK",
  "check_interval_minutes": 30,
  "searches": [
    {
      "keyword": "Montre",
      "category_code": "9800",
      "category_name": "9800 - Bijoux, pièces de collection, oeuvres d'art et artisanat, et plus",
      "enabled": true
    },
    {
      "keyword": "Guitare",
      "category_code": "7700",
      "category_name": "Instruments et accessoires de musique",
      "enabled": false
    }
  ]
}
```

### Obtenir un webhook Discord

1. Dans Discord → Paramètres du canal → Intégrations → Webhooks
2. Créer un nouveau webhook → Copier l'URL
3. Collez l'URL dans `discord_webhook_url`

### Codes de catégorie GCSurplus

| Code | Catégorie |
|------|-----------|
| 9800 | Bijoux, pièces de collection, oeuvres d'art et artisanat |
| 7800 | Équipement de sport et de camping |
| 7000 | Équipement d'ordinateurs, pièces et accessoires |
| 5800 | Équipement électronique et de communication |
| 6500 | Équipement médical, dentaire, scientifique |
| 7700 | Instruments et accessoires de musique |
| 7600 | Livres, cartes et autres publications |
| 2000 | Équipements et fournitures pour bateaux |

## Utilisation

### Exécution locale

```bash
# Surveillance continue (toutes les N minutes selon config.json)
python scraper.py

# Vérification unique (utile pour tester)
python scraper.py --once

# Test de la notification Discord
python scraper.py --test-discord
```

### Docker

```bash
# Construire l'image
docker build -t gcsurplus-monitor .

# Surveillance continue
docker run -d --name gcsurplus \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/seen_items.json:/app/seen_items.json \
  -v $(pwd)/scraper.log:/app/scraper.log \
  -e TZ=America/Toronto \
  --restart unless-stopped \
  gcsurplus-monitor

# Vérification unique
docker run --rm -v $(pwd)/config.json:/app/config.json:ro gcsurplus-monitor

# Test Discord
docker run --rm -v $(pwd)/config.json:/app/config.json:ro gcsurplus-monitor \
  python scraper.py --test-discord
```

### Docker Compose

```bash
# Démarrer la surveillance continue
docker compose up -d

# Voir les logs
docker compose logs -f

# Arrêter
docker compose down

# Test Discord (one-shot)
docker compose run --rm test-discord

# Vérification unique (one-shot)
docker compose run --rm once
```

## Fichiers générés

| Fichier | Description |
|---------|-------------|
| `config.json` | Configuration (webhook, fréquence, recherches) |
| `seen_items.json` | Lots déjà notifiés (pour éviter les doublons) |
| `scraper.log` | Journal d'exécution |

## Ajouter d'autres articles à surveiller

Il suffit d'ajouter des entrées dans le tableau `searches` de `config.json` :

```json
{
  "keyword": "Rolex",
  "category_code": "9800",
  "category_name": "9800 - Bijoux...",
  "enabled": true
}
```

Relancez ensuite le scraper.

## Horaire de surveillance

Le scraper suspend automatiquement les vérifications entre minuit et 6h00 du matin dans le fuseau horaire configuré. Cela permet de réduire les requêtes inutiles pendant les heures creuses.

## Licence

MIT
