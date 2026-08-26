#!/usr/bin/env python3
"""
Data models for GCSurplus Monitor.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Item:
    """Represents a scraped item from GCSurplus."""

    lot_number: str
    sale_number: str
    sale_ref: str  # ex: "R6TO0018662 - 6TO016165-EP976-JG"
    title: str
    description: str  # description complète
    current_bid: str
    min_bid: str
    close_date: str
    time_left: str
    location: str
    quantity: str
    sale_type: str
    condition: str
    image_url: str  # URL absolue de la 1re image
    all_image_urls: list
    url: str
    found_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SearchConfig:
    """Represents a search configuration."""

    keyword: str
    category_code: str
    category_name: str
    enabled: bool = True


@dataclass
class BidHistory:
    """Represents a bid in the history."""

    bid: str
    timestamp: str  # ISO format

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class TrackedItem:
    """Represents an item being tracked by a user."""

    lot_number: str
    sale_number: str
    title: str
    url: str
    current_bid: str
    min_bid: str
    close_date: str
    time_left: str
    location: str
    quantity: str
    sale_type: str
    condition: str
    image_url: str
    all_image_urls: list
    sale_ref: str
    description: str
    user_id: str  # Discord user ID who marked interested
    interested_at: str = field(default_factory=lambda: datetime.now().isoformat())
    bid_history: list = field(default_factory=list)  # List of BidHistory dicts
    alert_sent_24h: bool = False
    alert_sent_1h: bool = False
    alert_sent_15m: bool = False
    last_checked: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TrackedItem":
        """Reconstruct a TrackedItem from a JSON-deserialized dictionary."""
        return cls(
            lot_number=d.get("lot_number", ""),
            sale_number=d.get("sale_number", ""),
            title=d.get("title", ""),
            url=d.get("url", ""),
            current_bid=d.get("current_bid", "N/D"),
            min_bid=d.get("min_bid", "N/D"),
            close_date=d.get("close_date", "N/D"),
            time_left=d.get("time_left", "N/D"),
            location=d.get("location", "N/D"),
            quantity=d.get("quantity", "N/D"),
            sale_type=d.get("sale_type", "N/D"),
            condition=d.get("condition", "N/D"),
            image_url=d.get("image_url", ""),
            all_image_urls=d.get("all_image_urls", []),
            sale_ref=d.get("sale_ref", "N/D"),
            description=d.get("description", ""),
            user_id=d.get("user_id", ""),
            interested_at=d.get("interested_at", ""),
            bid_history=d.get("bid_history", []),
            alert_sent_24h=d.get("alert_sent_24h", False),
            alert_sent_1h=d.get("alert_sent_1h", False),
            alert_sent_15m=d.get("alert_sent_15m", False),
            last_checked=d.get("last_checked"),
        )
