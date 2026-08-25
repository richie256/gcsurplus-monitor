#!/usr/bin/env python3
"""
Storage utilities for persisting data to JSON files.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from models import TrackedItem

# File paths
CONFIG_FILE = Path(__file__).parent / "config.json"
SEEN_FILE = Path(__file__).parent / "seen_items.json"
TRACKED_FILE = Path(__file__).parent / "tracked_items.json"
LOG_FILE = Path(__file__).parent / "scraper.log"


def load_json(path: Path) -> dict:
    """Load JSON from a file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    """Save data to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config() -> dict:
    """Load configuration from config.json."""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_FILE}")
    return load_json(CONFIG_FILE)


def load_seen() -> set:
    """Load seen items lot numbers from seen_items.json."""
    if not SEEN_FILE.exists():
        return set()
    data = load_json(SEEN_FILE)
    return set(data.get("seen", []))


def save_seen(seen: set) -> None:
    """Save seen items lot numbers to seen_items.json."""
    save_json(SEEN_FILE, {"seen": sorted(seen)})


def load_tracked_items() -> Dict[str, TrackedItem]:
    """Load tracked items from tracked_items.json."""
    if not TRACKED_FILE.exists():
        return {}

    data = load_json(TRACKED_FILE)
    tracked = {}

    for lot_number, item_dict in data.get("tracked", {}).items():
        # Convert dict to TrackedItem
        tracked[lot_number] = TrackedItem(
            lot_number=item_dict.get("lot_number", ""),
            sale_number=item_dict.get("sale_number", ""),
            title=item_dict.get("title", ""),
            url=item_dict.get("url", ""),
            current_bid=item_dict.get("current_bid", "N/D"),
            min_bid=item_dict.get("min_bid", "N/D"),
            close_date=item_dict.get("close_date", "N/D"),
            time_left=item_dict.get("time_left", "N/D"),
            location=item_dict.get("location", "N/D"),
            quantity=item_dict.get("quantity", "N/D"),
            sale_type=item_dict.get("sale_type", "N/D"),
            condition=item_dict.get("condition", "N/D"),
            image_url=item_dict.get("image_url", ""),
            all_image_urls=item_dict.get("all_image_urls", []),
            sale_ref=item_dict.get("sale_ref", "N/D"),
            description=item_dict.get("description", ""),
            user_id=item_dict.get("user_id", ""),
            interested_at=item_dict.get("interested_at", ""),
            bid_history=item_dict.get("bid_history", []),
            alert_sent_24h=item_dict.get("alert_sent_24h", False),
            alert_sent_1h=item_dict.get("alert_sent_1h", False),
            alert_sent_15m=item_dict.get("alert_sent_15m", False),
            last_checked=item_dict.get("last_checked"),
        )

    return tracked


def save_tracked_items(tracked: Dict[str, TrackedItem]) -> None:
    """Save tracked items to tracked_items.json."""
    data = {
        "tracked": {
            lot_number: item.to_dict()
            for lot_number, item in tracked.items()
        }
    }
    save_json(TRACKED_FILE, data)


def track_item(item: TrackedItem) -> None:
    """Add or update a tracked item."""
    tracked = load_tracked_items()
    tracked[item.lot_number] = item
    save_tracked_items(tracked)


def untrack_item(lot_number: str) -> bool:
    """Remove a tracked item. Returns True if item was tracked."""
    tracked = load_tracked_items()
    if lot_number in tracked:
        del tracked[lot_number]
        save_tracked_items(tracked)
        return True
    return False


def get_tracked_item(lot_number: str) -> Optional[TrackedItem]:
    """Get a specific tracked item by lot number."""
    tracked = load_tracked_items()
    return tracked.get(lot_number)


def get_user_tracked_items(user_id: str) -> List[TrackedItem]:
    """Get all items tracked by a specific user."""
    tracked = load_tracked_items()
    return [item for item in tracked.values() if item.user_id == user_id]
