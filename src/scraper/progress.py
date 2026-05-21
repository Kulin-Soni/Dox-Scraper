import json
from pathlib import Path


class ProgressTracker:
    """Persists and restores pagination progress to/from a JSON file."""

    def __init__(self, location: Path) -> None:
        self.location = location if location.suffix == ".json" else location / "record.json"
        self.location.parent.mkdir(parents=True, exist_ok=True)

    def save(self, page: int, items: list | None) -> None:
        """Saves the current page and item list to disk."""
        with open(self.location, "w", encoding="utf-8") as file:
            json.dump({"page": page, "items": items}, file, ensure_ascii=False)

    def load(self) -> tuple[int, list]:
        """Loads progress from disk. Returns (1, []) if no saved state exists."""
        if not self.location.exists():
            return 1, []
        with open(self.location, encoding="utf-8") as file:
            data = json.load(file)
            return data["page"] or 1, data["items"]