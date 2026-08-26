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
- 🤝 Bouton **« Intéressé »** dans les notifications Discord pour suivre un article
- 📈 Suivi des mises et alertes automatiques à **24h, 1h et 15 min** avant la clôture

## Architecture

| Fichier | Rôle |
|---------|------|
| `scraper.py` | Boucle principale, scraping GCSurplus, notifications Discord |
| `bot.py` | Serveur Flask qui reçoit les interactions Discord (boutons) |
| `tracker.py` | Suivi des articles, détection de nouvelles mises, alertes de clôture |
| `storage.py` | Persistence JSON (`config`, `seen`, `tracked`) |
| `models.py` | Dataclasses (`Item`, `SearchConfig`, `TrackedItem`, `BidHistory`) |

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Éditez `config.json` (créé automatiquement au premier lancement avec des valeurs par défaut) :

```json
{
  "discord_webhook_url": "https://discord.com/api/webhooks/VOTRE_WEBHOOK",
  "discord_application_id": "VOTRE_APPLICATION_ID",
  "discord_public_key": "VOTRE_PUBLIC_KEY",
  "discord_bot_token": "VOTRE_BOT_TOKEN",
  "interaction_endpoint_port": 8080,
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

### Configurer le bot Discord (bouton « Intéressé »)

Le bouton « Intéressé » dans les notifications Discord permet aux utilisateurs de suivre un article. Cela nécessite un bot Discord avec un endpoint d'interaction :

1. Créez une application sur [discord.com/developers](https://discord.com/developers/applications)
2. Récupérez `Application ID` et `Public Key` → renseignez `discord_application_id` et `discord_public_key`
3. Créez un bot token → renseignez `discord_bot_token`
4. Dans les paramètres de l'application Discord, configurez l'**Interactions Endpoint URL** vers `http://VOTRE_SERVEUR:8080/interactions`
5. Le serveur Flask démarre automatiquement avec `scraper.py` sur le port `interaction_endpoint_port`

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
python3 scraper.py

# Vérification unique (utile pour tester)
python3 scraper.py --once

# Test de la notification Discord
python3 scraper.py --test-discord
```

### Docker

#### Build local image

```bash
# Construire l'image localement
docker build -t gcsurplus-monitor .
```

#### Using GitHub Container Registry (ghcr.io)

**First time setup (login):**
```bash
# Connecter avec votre compte GitHub
echo "TOKEN" | docker login ghcr.io -u USERNAME --password-stdin

# Ou utiliser gh CLI avec:
gh auth login
```

**Surveillance continue:**
```bash
# Utiliser l'image publique de GitHub Packages
docker run -d --name gcsurplus \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/seen_items.json:/app/seen_items.json \
  -v $(pwd)/tracked_items.json:/app/tracked_items.json \
  -v $(pwd)/scraper.log:/app/scraper.log \
  -p 8080:8080 \
  -e TZ=America/Toronto \
  --restart unless-stopped \
  ghcr.io/richie256/gcsurplus-monitor:latest
```

**Build and push to GitHub Packages:**
```bash
# Tag de version
docker tag gcsurplus-monitor ghcr.io/richie256/gcsurplus-monitor:latest
docker tag gcsurplus-monitor ghcr.io/richie256/gcsurplus-monitor:v1.0.0

# Puscher vers GitHub Packages
docker push ghcr.io/richie256/gcsurplus-monitor:latest
docker push ghcr.io/richie256/gcsurplus-monitor:v1.0.0
```

**Vérification unique:**
```bash
docker run --rm -v $(pwd)/config.json:/app/config.json:ro ghcr.io/richie256/gcsurplus-monitor:latest python3 scraper.py --once
```

**Test Discord:**
```bash
docker run --rm -v $(pwd)/config.json:/app/config.json:ro ghcr.io/richie256/gcsurplus-monitor:latest python3 scraper.py --test-discord
```

### Docker Compose

#### Using local image

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

#### Using GitHub Container Registry image

**Setup GitHub auth (first time only):**
```bash
docker login ghcr.io -u USERNAME -p TOKEN
# ou avec gh CLI: gh auth login
```

**Update docker-compose.yml:**
```yaml
services:
  gcsurplus:
    image: ghcr.io/richie256/gcsurplus-monitor:latest
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - ./config.json:/app/config.json:ro
      - ./seen_items.json:/app/seen_items.json
      - ./tracked_items.json:/app/tracked_items.json
      - ./scraper.log:/app/scraper.log
    environment:
      - TZ=America/Toronto
```

**Run:**
```bash
docker compose up -d
```

## Fichiers générés

| Fichier | Description |
|---------|-------------|
| `config.json` | Configuration (webhook, fréquence, recherches) — créé automatiquement si absent |
| `seen_items.json` | Lots déjà notifiés (pour éviter les doublons) |
| `tracked_items.json` | Articles suivis par les utilisateurs via le bouton « Intéressé » |
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
