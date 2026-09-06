from pathlib import Path
from typing import Any

import yaml


class FeedRegistry:
    """
    Loads and validates the configured Google News feeds.

    The registry is the single source of truth for feed configuration
    used by the ingestion pipeline.
    """

    ALLOWED_FEED_VALUES = {
        "market": {
            "india",
            "nifty",
            "sensex",
        },
        "macro": {
            "rbi",
            "economy",
        },
        "corporate": {
            "earnings",
            "actions",
        },
        "sector": {
            "it",
            "banks",
            "pharma",
            "auto",
            "fmcg",
            "metals",
            "oil_gas",
        },
        "index": {
            "nifty_50",
            "nifty_bank",
            "nifty_it",
            "nifty_midcap",
            "sensex",
        },
        "company": {
            "reliance",
            "tcs",
            "infosys",
            "hdfc_bank",
        },
        "mutual_fund": {
            "india",
        },
        "etf": {
            "gold",
        },
    }

    REQUIRED_FIELDS = {
        "feed_id",
        "feed_type",
        "feed_value",
        "query",
        "enabled",
    }

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Feed configuration not found: {self.config_path}"
            )

        self._feeds = self._load()

    def _load(self) -> list[dict[str, Any]]:
        with self.config_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            config = yaml.safe_load(file)

        if not isinstance(config, dict):
            raise ValueError("Feed configuration must be a YAML object.")

        feeds = config.get("feeds")

        if not isinstance(feeds, list):
            raise ValueError("'feeds' must be a YAML list.")

        self._validate(feeds)

        return feeds

    def _validate(self, feeds: list[dict[str, Any]]) -> None:
        feed_ids = set()

        for index, feed in enumerate(feeds):
            if not isinstance(feed, dict):
                raise ValueError(
                    f"Feed at index {index} must be an object."
                )

            missing_fields = self.REQUIRED_FIELDS - feed.keys()

            if missing_fields:
                raise ValueError(
                    f"Feed at index {index} is missing fields: "
                    f"{sorted(missing_fields)}"
                )

            feed_id = feed["feed_id"]
            feed_type = feed["feed_type"]
            feed_value = feed["feed_value"]

            # ----------------------------------------------------------
            # Validate feed type
            # ----------------------------------------------------------

            if feed_type not in self.ALLOWED_FEED_VALUES:
                raise ValueError(
                    f"Invalid feed_type '{feed_type}' "
                    f"for feed '{feed_id}'."
                )

            # ----------------------------------------------------------
            # Validate feed value
            # ----------------------------------------------------------

            allowed_values = self.ALLOWED_FEED_VALUES[feed_type]

            if feed_value not in allowed_values:
                raise ValueError(
                    f"Invalid feed_value '{feed_value}' "
                    f"for feed_type '{feed_type}'."
                )

            # ----------------------------------------------------------
            # Validate deterministic feed ID
            # ----------------------------------------------------------

            expected_feed_id = f"{feed_type}_{feed_value}"

            if feed_id != expected_feed_id:
                raise ValueError(
                    f"Invalid feed_id '{feed_id}'. "
                    f"Expected '{expected_feed_id}'."
                )

            # ----------------------------------------------------------
            # Validate uniqueness
            # ----------------------------------------------------------

            if feed_id in feed_ids:
                raise ValueError(
                    f"Duplicate feed_id detected: '{feed_id}'."
                )

            feed_ids.add(feed_id)

            # ----------------------------------------------------------
            # Validate query
            # ----------------------------------------------------------

            if not isinstance(feed["query"], str) or not feed["query"].strip():
                raise ValueError(
                    f"Query cannot be empty for feed '{feed_id}'."
                )

            # ----------------------------------------------------------
            # Validate enabled flag
            # ----------------------------------------------------------

            if not isinstance(feed["enabled"], bool):
                raise ValueError(
                    f"'enabled' must be boolean for feed '{feed_id}'."
                )

    def all(self) -> list[dict[str, Any]]:
        """Return all configured feeds."""
        return list(self._feeds)

    def enabled(self) -> list[dict[str, Any]]:
        """Return only enabled feeds."""
        return [
            feed
            for feed in self._feeds
            if feed["enabled"]
        ]

    def get(self, feed_id: str) -> dict[str, Any]:
        """Return a feed by ID."""
        for feed in self._feeds:
            if feed["feed_id"] == feed_id:
                return dict(feed)

        raise KeyError(
            f"Unknown feed_id: '{feed_id}'"
        )

    def count(self) -> int:
        """Return total configured feed count."""
        return len(self._feeds)