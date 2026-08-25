#!/usr/bin/env python3
"""
Data models for GCSurplus Monitor.
"""

from dataclasses import dataclass, field
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
        return {
            "bid": self.bid,
            "timestamp": self.timestamp,
        }


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
        return {
            "lot_number": self.lot_number,
            "sale_number": self.sale_number,
            "title": self.title,
            "url": self.url,
            "current_bid": self.current_bid,
            "min_bid": self.min_bid,
            "close_date": self.close_date,
            "time_left": self.time_left,
            "location": self.location,
            "quantity": self.quantity,
            "sale_type": self.sale_type,
            "condition": self.condition,
            "image_url": self.image_url,
            "all_image_urls": self.all_image_urls,
            "sale_ref": self.sale_ref,
            "description": self.description,
            "user_id": self.user_id,
            "interested_at": self.interested_at,
            "bid_history": self.bid_history,
            "alert_sent_24h": self.alert_sent_24h,
            "alert_sent_1h": self.alert_sent_1h,
            "alert_sent_15m": self.alert_sent_15m,
            "last_checked": self.last_checked,
        }

    @classmethod
    def from_item(cls, item: Item, user_id: str) -> "TrackedItem":
        """Create a TrackedItem from an Item and user ID."""
        return cls(
            lot_number=item.lot_number,
            sale_number=item.sale_number,
            title=item.title,
            url=item.url,
            current_bid=item.current_bid,
            min_bid=item.min_bid,
            close_date=item.close_date,
            time_left=item.time_left,
            location=item.location,
            quantity=item.quantity,
            sale_type=item.sale_type,
            condition=item.condition,
            image_url=item.image_url,
            all_image_urls=item.all_image_urls,
            sale_ref=item.sale_ref,
            description=item.description,
            user_id=user_id,
            bid_history=[],
        )
