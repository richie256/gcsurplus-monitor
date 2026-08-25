#!/usr/bin/env python3
"""
Item tracking and alert system for GCSurplus Monitor.

This module handles:
- Checking tracked items for bid updates
- Parsing close dates (French month names)
- Sending alerts at 24h, 1h, and 15min before auction close
"""

import logging
import re
from datetime import datetime, timedelta

import requests

from models import BidHistory, TrackedItem
from storage import load_tracked_items, save_tracked_items, untrack_item

# ─────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  French Month Names
# ─────────────────────────────────────────────

FRENCH_MONTHS = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    # Accented variants
    "fevrier": 2,
    "aout": 8,
    "decembre": 12,
}

# ─────────────────────────────────────────────
#  Alert Thresholds
# ─────────────────────────────────────────────

ALERT_THRESHOLDS = [
    ("alert_sent_24h", timedelta(hours=24), "24 hours"),
    ("alert_sent_1h", timedelta(hours=1), "1 hour"),
    ("alert_sent_15m", timedelta(minutes=15), "15 minutes"),
]


# ─────────────────────────────────────────────
#  Close Date Parsing
# ─────────────────────────────────────────────


def parse_close_date(close_date_str: str) -> datetime | None:
    """
    Parse close date string from GCSurplus.

    Format: "25-août-2026 @ 09h00" or similar
    Returns: datetime object or None if parsing fails
    """
    if not close_date_str or close_date_str == "N/D":
        return None

    # Pattern: DD-Month-YYYY @ HHhMM
    # Examples: "25-août-2026 @ 09h00", "1-septembre-2026 @ 14h30"
    pattern = r"(\d{1,2})-([a-zéû]+)-(\d{4})\s*@\s*(\d{1,2})h(\d{2})"
    match = re.search(pattern, close_date_str.lower(), re.IGNORECASE)

    if not match:
        log.debug(f"Could not parse close date: {close_date_str}")
        return None

    day = int(match.group(1))
    month_name = match.group(2).lower()
    year = int(match.group(3))
    hour = int(match.group(4))
    minute = int(match.group(5))

    # Convert French month name to number
    month = FRENCH_MONTHS.get(month_name)
    if not month:
        log.warning(f"Unknown French month: {month_name}")
        return None

    try:
        return datetime(year, month, day, hour, minute)
    except ValueError as e:
        log.error(f"Invalid date values: {e}")
        return None


def format_time_remaining(delta: timedelta) -> str:
    """Format timedelta as human-readable string."""
    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        return "Auction ended"

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0 and days == 0:  # Only show minutes if < 1 day
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")

    return " ".join(parts) if parts else "Less than 1 minute"


# ─────────────────────────────────────────────
#  Bid Price Parsing
# ─────────────────────────────────────────────


def parse_bid_amount(bid_str: str) -> float | None:
    """
    Parse bid string to float.

    Examples: "$6,200.00" -> 6200.0, "$100" -> 100.0
    """
    if not bid_str or bid_str == "N/D":
        return None

    # Remove currency symbol and commas
    cleaned = bid_str.replace("$", "").replace(",", "").strip()

    try:
        return float(cleaned)
    except ValueError:
        return None


# ─────────────────────────────────────────────
#  Item Re-scraping
# ─────────────────────────────────────────────


def fetch_tracked_item_update(item: TrackedItem, session: requests.Session) -> dict | None:
    """
    Re-scrape item page to get current bid and time left.

    Returns dict with updated fields or None if fetch fails.
    """
    from scraper import fetch_item_detail

    try:
        ref = {
            "lot": item.lot_number,
            "sale": item.sale_number,
            "title": item.title,
            "url": item.url,
        }

        # Use existing scraper function
        updated = fetch_item_detail(ref, session)

        return {
            "current_bid": updated.current_bid,
            "min_bid": updated.min_bid,
            "close_date": updated.close_date,
            "time_left": updated.time_left,
        }
    except Exception as e:
        log.error(f"Failed to fetch update for item {item.lot_number}: {e}")
        return None


# ─────────────────────────────────────────────
#  Alert Checking
# ─────────────────────────────────────────────


def check_alert_needed(item: TrackedItem, now: datetime) -> tuple[bool, str, str]:
    """
    Check if an alert should be sent for this item.

    Returns: (should_alert, alert_type, alert_message)
    """
    close_dt = parse_close_date(item.close_date)
    if not close_dt:
        return False, "", ""

    time_remaining = close_dt - now

    # Check if auction has ended
    if time_remaining.total_seconds() <= 0:
        return True, "ended", f"🔨 Auction ended for **{item.title}**"

    # Check thresholds from longest to shortest
    for alert_flag, threshold, label in ALERT_THRESHOLDS:
        if time_remaining <= threshold:
            # Check if alert already sent
            if getattr(item, alert_flag, False):
                continue

            return (
                True,
                alert_flag,
                (
                    f"⏰ **{label} remaining** for [{item.title}]({item.url})\n"
                    f"Current bid: **{item.current_bid}**\n"
                    f"Time left: {format_time_remaining(time_remaining)}"
                ),
            )

    return False, "", ""


# ─────────────────────────────────────────────
#  Main Tracking Loop
# ─────────────────────────────────────────────


def check_tracked_items(session: requests.Session, webhook_url: str) -> int:
    """
    Check all tracked items for updates and send alerts.

    Returns: Number of notifications sent
    """
    tracked = load_tracked_items()
    if not tracked:
        return 0

    log.info(f"🔍 Checking {len(tracked)} tracked item(s) for updates")
    notifications_sent = 0
    now = datetime.now()

    for lot_number, item in list(tracked.items()):
        # Fetch current state
        updates = fetch_tracked_item_update(item, session)
        if not updates:
            log.warning(f"Could not fetch updates for {lot_number}")
            continue

        # Check for bid changes
        old_bid = parse_bid_amount(item.current_bid)
        new_bid = parse_bid_amount(updates["current_bid"])

        if new_bid and old_bid and new_bid > old_bid:
            # Record bid history
            bid_entry = BidHistory(bid=updates["current_bid"], timestamp=now.isoformat())
            item.bid_history.append(
                bid_entry.to_dict()
                if hasattr(bid_entry, "to_dict")
                else {
                    "bid": bid_entry.bid,
                    "timestamp": bid_entry.timestamp,
                }
            )

            # Send bid update notification
            send_bid_notification(item, updates["current_bid"], old_bid, webhook_url)
            notifications_sent += 1

            # Update item
            item.current_bid = updates["current_bid"]

        # Update other fields
        item.min_bid = updates["min_bid"]
        item.close_date = updates["close_date"]
        item.time_left = updates["time_left"]
        item.last_checked = now.isoformat()

        # Check for alerts
        should_alert, alert_type, alert_msg = check_alert_needed(item, now)
        if should_alert:
            if alert_type == "ended":
                # Auction ended - remove from tracking
                send_auction_ended_notification(item, webhook_url)
                untrack_item(lot_number)
                log.info(f"🗑️ Removed ended auction: {lot_number}")
            else:
                # Time-based alert
                send_alert_notification(item, alert_msg, webhook_url)
                setattr(item, alert_type, True)
                notifications_sent += 1

        # Save updates
        save_tracked_items(dict(tracked.items()))

    return notifications_sent


def send_bid_notification(item: TrackedItem, new_bid: str, old_bid: float, webhook_url: str) -> None:
    """Send notification about bid increase."""
    import requests

    content = (
        f"📈 **Bid increased!**\n"
        f"[{item.title}]({item.url})\n"
        f"Previous: ${old_bid:,.2f} → **{new_bid}**\n"
        f"<@{item.user_id}>"
    )

    payload = {
        "username": "GCSurplus Tracker 📊",
        "content": content,
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
        log.info(f"✅ Bid notification sent for {item.lot_number}")
    except Exception as e:
        log.error(f"Failed to send bid notification: {e}")


def send_alert_notification(item: TrackedItem, alert_msg: str, webhook_url: str) -> None:
    """Send time-based alert notification."""
    import requests

    payload = {
        "username": "GCSurplus Tracker ⏰",
        "content": f"{alert_msg}\n<@{item.user_id}>",
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
        log.info(f"✅ Alert sent for {item.lot_number}")
    except Exception as e:
        log.error(f"Failed to send alert: {e}")


def send_auction_ended_notification(item: TrackedItem, webhook_url: str) -> None:
    """Send notification that auction has ended."""
    import requests

    content = f"🔨 **Auction ended!**\n[{item.title}]({item.url})\nFinal bid: **{item.current_bid}**\n<@{item.user_id}>"

    payload = {
        "username": "GCSurplus Tracker 🔨",
        "content": content,
    }

    try:
        requests.post(webhook_url, json=payload, timeout=10)
        log.info(f"✅ Auction ended notification sent for {item.lot_number}")
    except Exception as e:
        log.error(f"Failed to send auction ended notification: {e}")


# ─────────────────────────────────────────────
#  Testing
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

    # Test close date parsing
    test_dates = [
        "25-août-2026 @ 09h00",
        "1-septembre-2026 @ 14h30",
        "31-décembre-2026 @ 23h59",
    ]

    print("Testing close date parsing:")
    for date_str in test_dates:
        parsed = parse_close_date(date_str)
        if parsed:
            delta = parsed - datetime.now()
            print(f"  {date_str} → {parsed} ({format_time_remaining(delta)})")
        else:
            print(f"  {date_str} → FAILED TO PARSE")
