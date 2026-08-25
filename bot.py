#!/usr/bin/env python3
"""
Discord bot for handling "Interested" button interactions.

This module provides an HTTP endpoint that receives Discord interactions
and handles button clicks for tracking items.
"""

import json
import logging
import threading

from flask import Flask, jsonify, request

try:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    VerifyKey = None
    BadSignatureError = None

from models import TrackedItem
from storage import get_tracked_item, track_item

# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Flask App
# ─────────────────────────────────────────────

app = Flask(__name__)

# Will be set from config
PUBLIC_KEY: str | None = None
APPLICATION_ID: str | None = None
WEBHOOK_URL: str | None = None


def verify_discord_signature(public_key: str, data: bytes, signature: str, timestamp: str) -> bool:
    """Verify Discord request signature using Ed25519."""
    if not CRYPTO_AVAILABLE:
        log.warning("PyNaCl not installed - skipping signature verification (unsafe for production)")
        return True

    try:
        verify_key = VerifyKey(bytes.fromhex(public_key))
        message = timestamp.encode() + data
        verify_key.verify(message, bytes.fromhex(signature))
        return True
    except (BadSignatureError, Exception) as e:
        log.error(f"Signature verification failed: {e}")
        return False


@app.route('/interactions', methods=['POST'])
def handle_interaction():
    """Handle incoming Discord interaction."""
    # Verify signature
    signature = request.headers.get('X-Signature-Ed25519', '')
    timestamp = request.headers.get('X-Signature-Timestamp', '')

    if PUBLIC_KEY and not verify_discord_signature(PUBLIC_KEY, signature, timestamp, request.data):
        return jsonify({'error': 'Invalid signature'}), 401

    data = request.json
    interaction_type = data.get('type')

    # PING - Discord verification
    if interaction_type == 1:
        return jsonify({'type': 1})

    # APPLICATION_COMMAND
    if interaction_type == 2:
        return jsonify({'type': 4, 'data': {'content': 'Pong!'}})

    # MESSAGE_COMPONENT (button click)
    if interaction_type == 3:
        return handle_button_click(data)

    return jsonify({'error': 'Unknown interaction type'}), 400


def handle_button_click(data: dict) -> tuple:
    """Handle button click interaction."""
    custom_id = data['data']['custom_id']
    user_id = data['member']['user']['id']
    user_name = data['member']['user'].get('username', 'Unknown')
    message = data.get('message', {})

    log.info(f"Button clicked: {custom_id} by user {user_name} ({user_id})")

    # Handle "Interested" button
    if custom_id.startswith('interested_'):
        lot_number = custom_id.replace('interested_', '')

        # Check if already tracked
        existing = get_tracked_item(lot_number)
        if existing:
            return jsonify({
                'type': 4,
                'data': {
                    'content': "⚠️ Item already tracked by another user.",
                    'flags': 64  # Ephemeral - only visible to user
                }
            })

        # Extract item data from the message embed
        embed = message.get('embeds', [{}])[0] if message.get('embeds') else {}
        fields = {f['name']: f['value'] for f in embed.get('fields', [])}

        # Extract URL from embed
        item_url = embed.get('url', '')

        # Create tracked item from message data
        # We need to reconstruct enough data to track
        tracked = TrackedItem(
            lot_number=lot_number,
            sale_number='',  # Will be filled by tracker
            title=embed.get('title', '').replace('🆕  ', ''),
            url=item_url,
            current_bid=fields.get('💰 Mise actuelle', 'N/D').replace('**', ''),
            min_bid=fields.get('📈 Prochaine mise min.', 'N/D'),
            close_date=fields.get('📅 Date de clôture', 'N/D'),
            time_left=fields.get('⏳ Temps restant', 'N/D'),
            location=fields.get('📍 Emplacement', 'N/D'),
            quantity=fields.get('📦 Quantité', 'N/D'),
            sale_type=fields.get('🏷️ Type de vente', 'N/D'),
            condition=fields.get('🔍 État', 'N/D'),
            image_url=embed.get('image', {}).get('url', ''),
            all_image_urls=[embed.get('image', {}).get('url', '')] if embed.get('image') else [],
            sale_ref=fields.get('🔢 Réf. Vente / Lot', 'N/D').replace('`', ''),
            description='',
            user_id=user_id,
        )

        # Save to tracked items
        track_item(tracked)

        log.info(f"✅ Item {lot_number} tracked by user {user_id}")

        return jsonify({
            'type': 4,
            'data': {
                'content': "✅ Tracking this item! I'll notify you of bid changes and before auction close.",
                'flags': 64  # Ephemeral
            }
        })

    # Handle "Untrack" button (optional future feature)
    if custom_id.startswith('untrack_'):
        lot_number = custom_id.replace('untrack_', '')
        from storage import untrack_item

        existing = get_tracked_item(lot_number)
        if existing and existing.user_id == user_id:
            untrack_item(lot_number)
            return jsonify({
                'type': 4,
                'data': {
                    'content': f"✅ Stopped tracking item {lot_number}.",
                    'flags': 64
                }
            })
        else:
            return jsonify({
                'type': 4,
                'data': {
                    'content': "⚠️ You are not tracking this item.",
                    'flags': 64
                }
            })

    return jsonify({
        'type': 4,
        'data': {'content': 'Unknown button action', 'flags': 64}
    })


def start_bot_server(config: dict, host: str = '0.0.0.0', port: int = 8080) -> threading.Thread:
    """
    Start the Flask server in a background thread.

    Args:
        config: Configuration dict with discord_public_key, discord_application_id
        host: Host to bind to
        port: Port to listen on

    Returns:
        Thread running the Flask server
    """
    global PUBLIC_KEY, APPLICATION_ID, WEBHOOK_URL

    PUBLIC_KEY = config.get('discord_public_key', '')
    APPLICATION_ID = config.get('discord_application_id', '')
    WEBHOOK_URL = config.get('discord_webhook_url', '')

    if not PUBLIC_KEY and CRYPTO_AVAILABLE:
        log.warning("No Discord public key configured - signature verification disabled")

    def run_server():
        log.info(f"🌐 Starting Discord interaction server on port {port}")
        app.run(host=host, port=port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    log.info("✅ Discord bot server thread started")

    return thread


# ─────────────────────────────────────────────
#  CLI for testing
# ─────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("🧪 Testing Discord interaction server...")
    print("This is for development only. Use the main scraper.py for production.")

    # Load config
    import json
    from pathlib import Path

    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        config = json.load(open(config_file))
    else:
        config = {}

    port = config.get('interaction_endpoint_port', 8080)
    start_bot_server(config, port=port)

    # Keep main thread alive
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
