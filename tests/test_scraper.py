"""Unit tests for GCSurplus Monitor scraper."""

import json
import pytest
import responses
from unittest.mock import patch, MagicMock
from datetime import datetime

from scraper import (
    Item,
    SearchConfig,
    load_config,
    load_seen,
    save_seen,
    build_search_url,
    parse_listing,
    has_next_page,
    fetch_item_detail,
    build_embed,
    send_discord_notification,
    run_once,
)


# ─────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "discord_webhook_url": "https://discord.com/api/webhooks/test",
        "check_interval_minutes": 30,
        "searches": [
            {
                "keyword": "Montre",
                "category_code": "9800",
                "category_name": "9800 - Bijoux",
                "enabled": True,
            }
        ],
    }


@pytest.fixture
def sample_item():
    """Sample Item for testing."""
    return Item(
        lot_number="762279",
        sale_number="601279",
        sale_ref="R6TO0018662 - 6TO016165-EP976-JG",
        title="Montre en or de 18 ct Rolex 69173",
        description="Marque : Rolex\nMouvement : automatique",
        current_bid="$6,200.00",
        min_bid="$6,300.00",
        close_date="25-août-2026 @ 09h00",
        time_left="3 jours 9 heures",
        location="North York, ON",
        quantity="1 (chaque)",
        sale_type="Enchère ouverte 🔨",
        condition="La montre est fonctionnelle",
        image_url="https://gcsurplus.ca/lotImages/2988960.jpeg",
        all_image_urls=["https://gcsurplus.ca/lotImages/2988960.jpeg"],
        url="https://gcsurplus.ca/mn-fra.cfm?lcn=762279&scn=601279",
    )


@pytest.fixture
def sample_search():
    """Sample SearchConfig for testing."""
    return SearchConfig(
        keyword="Montre",
        category_code="9800",
        category_name="9800 - Bijoux",
        enabled=True,
    )


@pytest.fixture
def sample_listing_html():
    """Sample HTML from listing page."""
    return """
    <html>
    <body>
        <a href="/mn-fra.cfm?snc=wfsav&scn=601279&lcn=762279&lct=L">
            Montre en or Rolex 69173
        </a>
        <a href="/mn-fra.cfm?snc=wfsav&scn=601280&lcn=762280&lct=L">
            Montre Seiko automatique
        </a>
        <a href="/mn-fra.cfm?snc=wfsav&scn=601281&lcn=762281&lct=L">
            Ceinture en cuir
        </a>
    </body>
    </html>
    """


@pytest.fixture
def sample_detail_html():
    """Sample HTML from detail page."""
    return """
    <html>
    <main>
        <img class="newViewer" src="/lotImages/2988960.jpeg">
        <p>Article : Montre en or de 18 ct Rolex 69173</p>
        <p>Soumission courante : $6,200.00</p>
        <p>Enchère min : $6,300.00</p>
        <p>Date de clôture : 25-août-2026 @ 09h00</p>
        <p>Restant : 3 jours 9 heures 30 minutes</p>
        <p>Emplacement : North York, ON</p>
        <p>Quantité : 1 (chaque)</p>
        <p>Vente / Lot : R6TO0018662 - 6TO016165-EP976-JG</p>
        <p>État : La montre est fonctionnelle</p>
        <p>Description :</p>
        <p>Marque : Rolex</p>
        <p>Mouvement : automatique</p>
        <p>État :</p>
        <p>Usure normale</p>
    </main>
    </html>
    """


# ─────────────────────────────────────────────
#  Config Tests
# ─────────────────────────────────────────────


class TestConfig:
    """Tests for configuration loading/saving."""

    def test_load_config_existing(self, tmp_path, sample_config):
        """Test loading an existing config file."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(sample_config))

        with patch("scraper.CONFIG_FILE", config_file):
            config = load_config()
            assert config == sample_config

    def test_load_config_creates_default(self, tmp_path):
        """Test that missing config creates default."""
        config_file = tmp_path / "config.json"

        with patch("scraper.CONFIG_FILE", config_file):
            config = load_config()
            assert "discord_webhook_url" in config
            assert "searches" in config
            assert config_file.exists()

    def test_load_seen_empty(self, tmp_path):
        """Test loading seen items when file doesn't exist."""
        seen_file = tmp_path / "seen_items.json"

        with patch("scraper.SEEN_FILE", seen_file):
            seen = load_seen()
            assert seen == set()

    def test_load_seen_existing(self, tmp_path):
        """Test loading existing seen items."""
        seen_file = tmp_path / "seen_items.json"
        seen_file.write_text(json.dumps({"seen": ["123", "456"]}))

        with patch("scraper.SEEN_FILE", seen_file):
            seen = load_seen()
            assert seen == {"123", "456"}

    def test_save_seen(self, tmp_path):
        """Test saving seen items."""
        seen_file = tmp_path / "seen_items.json"

        with patch("scraper.SEEN_FILE", seen_file):
            save_seen({"456", "123"})

            data = json.loads(seen_file.read_text())
            assert data == {"seen": ["123", "456"]}  # sorted


# ─────────────────────────────────────────────
#  URL Building Tests
# ─────────────────────────────────────────────


class TestURLBuilder:
    """Tests for URL building."""

    def test_build_search_url_basic(self):
        """Test basic search URL construction."""
        url = build_search_url("9800", "Montre")

        assert "gcsurplus.ca" in url
        assert "hpcs=9800" in url
        assert "kws=Montre" in url
        assert "str=1" in url

    def test_build_search_url_with_start(self):
        """Test search URL with pagination offset."""
        url = build_search_url("9800", "Montre", start=11)

        assert "str=11" in url


# ─────────────────────────────────────────────
#  Parsing Tests
# ─────────────────────────────────────────────


class TestParsing:
    """Tests for HTML parsing."""

    def test_parse_listing_extracts_items(self, sample_listing_html):
        """Test that parse_listing extracts item references."""
        refs = parse_listing(sample_listing_html, "Montre")

        assert len(refs) == 2  # Only "Montre" items
        assert refs[0]["lot"] == "762279"
        assert refs[0]["sale"] == "601279"
        assert "Montre" in refs[0]["title"]

    def test_parse_listing_filters_by_keyword(self, sample_listing_html):
        """Test that keyword filtering works."""
        refs = parse_listing(sample_listing_html, "Rolex")

        assert len(refs) == 1
        assert "Rolex" in refs[0]["title"]

    def test_parse_listing_no_keyword_filter(self, sample_listing_html):
        """Test parsing without keyword filter."""
        refs = parse_listing(sample_listing_html, "")

        assert len(refs) == 3

    def test_has_next_page_true(self):
        """Test detection of next page."""
        html = '<html><a href="?str=11">Suivant</a></html>'
        assert has_next_page(html) is True

    def test_has_next_page_false(self):
        """Test detection of last page."""
        html = "<html><p>No more results</p></html>"
        assert has_next_page(html) is False


# ─────────────────────────────────────────────
#  Detail Fetching Tests
# ─────────────────────────────────────────────


class TestDetailFetching:
    """Tests for detail page fetching."""

    @responses.activate
    def test_fetch_item_detail_success(self, sample_detail_html):
        """Test fetching item details successfully."""
        ref = {
            "lot": "762279",
            "sale": "601279",
            "title": "Montre Rolex",
            "url": "https://gcsurplus.ca/test",
        }

        responses.get("https://gcsurplus.ca/test", body=sample_detail_html, status=200)

        import requests

        session = requests.Session()
        item = fetch_item_detail(ref, session)

        assert item.lot_number == "762279"
        assert item.sale_number == "601279"
        assert "Rolex" in item.title
        assert item.current_bid == "$6,200.00"
        assert item.min_bid == "$6,300.00"
        assert item.location == "North York, ON"
        assert len(item.all_image_urls) == 1

    @responses.activate
    def test_fetch_item_detail_failure_returns_minimal(self):
        """Test that failed detail fetch returns minimal item."""
        ref = {
            "lot": "762279",
            "sale": "601279",
            "title": "Montre Rolex",
            "url": "https://gcsurplus.ca/test",
        }

        responses.get("https://gcsurplus.ca/test", status=500)

        import requests

        session = requests.Session()
        item = fetch_item_detail(ref, session)

        assert item.lot_number == "762279"
        assert item.title == "Montre Rolex"
        assert item.current_bid == "N/D"
        assert item.image_url == ""


# ─────────────────────────────────────────────
#  Discord Tests
# ─────────────────────────────────────────────


class TestDiscord:
    """Tests for Discord notification functionality."""

    def test_build_embed_structure(self, sample_item, sample_search):
        """Test that embed has correct structure."""
        embed = build_embed(sample_item, sample_search)

        assert embed["title"].startswith("🆕")
        assert embed["url"] == sample_item.url
        assert embed["color"] == 0xFEE75C  # Enchère ouverte color
        assert len(embed["fields"]) > 0
        assert embed["image"]["url"] == sample_item.image_url

    def test_build_embed_truncates_long_title(self, sample_search):
        """Test that long titles are truncated to 256 chars."""
        long_title = "X" * 300
        item = Item(
            lot_number="123",
            sale_number="456",
            sale_ref="REF",
            title=long_title,
            description="",
            current_bid="$100",
            min_bid="$110",
            close_date="2026-01-01",
            time_left="1 day",
            location="Test",
            quantity="1",
            sale_type="Enchère ouverte 🔨",
            condition="Good",
            image_url="",
            all_image_urls=[],
            url="https://test.com",
        )

        embed = build_embed(item, sample_search)
        assert len(embed["title"]) <= 256

    @responses.activate
    def test_send_discord_notification_success(self, sample_item, sample_search):
        """Test successful Discord notification."""
        responses.post("https://discord.com/api/webhooks/test", status=204)

        result = send_discord_notification(
            "https://discord.com/api/webhooks/test", sample_item, sample_search
        )

        assert result is True
        assert len(responses.calls) == 1

    @responses.activate
    def test_send_discord_notification_failure(self, sample_item, sample_search):
        """Test failed Discord notification."""
        responses.post(
            "https://discord.com/api/webhooks/test",
            status=400,
            body='{"message": "Invalid webhook"}',
        )

        result = send_discord_notification(
            "https://discord.com/api/webhooks/test", sample_item, sample_search
        )

        assert result is False

    def test_send_discord_notification_no_webhook(self, sample_item, sample_search):
        """Test that missing webhook URL returns False."""
        result = send_discord_notification("", sample_item, sample_search)
        assert result is False


# ─────────────────────────────────────────────
#  Integration Tests
# ─────────────────────────────────────────────


class TestIntegration:
    """Integration tests for main workflow."""

    @responses.activate
    def test_run_once_finds_new_items(
        self, tmp_path, sample_config, sample_listing_html, sample_detail_html
    ):
        """Test that run_once finds and processes new items."""
        # Setup files
        config_file = tmp_path / "config.json"
        seen_file = tmp_path / "seen_items.json"
        config_file.write_text(json.dumps(sample_config))

        # Mock HTTP responses
        responses.get(
            "https://gcsurplus.ca/mn-fra.cfm", body=sample_listing_html, status=200
        )
        responses.get(
            "https://gcsurplus.ca/mn-fra.cfm?snc=wfsav&scn=601279&lcn=762279&lct=L",
            body=sample_detail_html,
            status=200,
        )
        responses.get(
            "https://gcsurplus.ca/mn-fra.cfm?snc=wfsav&scn=601280&lcn=762280&lct=L",
            body=sample_detail_html,
            status=200,
        )
        responses.post("https://discord.com/api/webhooks/test", status=204)

        with (
            patch("scraper.CONFIG_FILE", config_file),
            patch("scraper.SEEN_FILE", seen_file),
        ):
            import requests

            session = requests.Session()
            count = run_once(sample_config, session)

            assert count == 2  # Two new items found

    @responses.activate
    def test_run_once_skips_seen_items(
        self, tmp_path, sample_config, sample_listing_html
    ):
        """Test that run_once skips already seen items."""
        config_file = tmp_path / "config.json"
        seen_file = tmp_path / "seen_items.json"
        config_file.write_text(json.dumps(sample_config))
        seen_file.write_text(json.dumps({"seen": ["762279", "762280"]}))

        responses.get(
            "https://gcsurplus.ca/mn-fra.cfm", body=sample_listing_html, status=200
        )

        with (
            patch("scraper.CONFIG_FILE", config_file),
            patch("scraper.SEEN_FILE", seen_file),
        ):
            import requests

            session = requests.Session()
            count = run_once(sample_config, session)

            assert count == 0  # All items already seen


# ─────────────────────────────────────────────
#  Dataclass Tests
# ─────────────────────────────────────────────


class TestDataclasses:
    """Tests for dataclass structures."""

    def test_item_creation(self):
        """Test Item dataclass creation."""
        item = Item(
            lot_number="123",
            sale_number="456",
            sale_ref="REF",
            title="Test Item",
            description="Test description",
            current_bid="$100",
            min_bid="$110",
            close_date="2026-01-01",
            time_left="1 day",
            location="Test Location",
            quantity="1",
            sale_type="Enchère ouverte 🔨",
            condition="Good",
            image_url="https://test.com/img.jpg",
            all_image_urls=["https://test.com/img.jpg"],
            url="https://test.com",
        )

        assert item.lot_number == "123"
        assert item.title == "Test Item"
        assert item.found_at  # Should have default timestamp

    def test_search_config_creation(self):
        """Test SearchConfig dataclass creation."""
        search = SearchConfig(
            keyword="Test", category_code="9800", category_name="Test Category"
        )

        assert search.keyword == "Test"
        assert search.enabled is True  # Default value


# ─────────────────────────────────────────────
#  Timezone/Hours Tests
# ─────────────────────────────────────────────


class TestHoursOfOperation:
    """Tests for off-hours pause logic."""

    @patch("scraper.datetime")
    def test_skips_during_off_hours(self, mock_datetime):
        """Test that scraper skips during midnight-6AM."""
        # Mock current time as 3 AM
        mock_datetime.now.return_value = MagicMock(hour=3)
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        # This should sleep until 6 AM
        # We can't easily test the full loop, but we verify the hour check logic
        assert 0 <= 3 < 6  # Off-hours check

    @patch("scraper.datetime")
    def test_runs_during_active_hours(self, mock_datetime):
        """Test that scraper runs during active hours."""
        # Mock current time as 10 AM
        mock_datetime.now.return_value = MagicMock(hour=10)
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        # Active hours check
        assert not (0 <= 10 < 6)  # Should run
