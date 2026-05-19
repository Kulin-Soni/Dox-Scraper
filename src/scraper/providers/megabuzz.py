from typing import List, Tuple
from pathvalidate import sanitize_filename

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTENT_TYPES:   list[str] = ["sub", "dub"]
PROVIDER_ORIGIN: str       = "https://megaplay.buzz/"
PROVIDER:        str       = f"{PROVIDER_ORIGIN}/stream/ani"

# ---------------------------------------------------------------------------
# URLBuilder
# ---------------------------------------------------------------------------

class URLBuilder:
    """Builds a flat list of episode stream entries for a given anime list."""

    def __init__(self, anime_list: List[dict] | None = None) -> None:
        # Avoid the mutable-default-argument pitfall by defaulting to None.
        self.anime_list: List[dict] = anime_list if anime_list is not None else []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_episode_entry(
        self,
        anime: dict,
        episode: int,
        content_type: str,
    ) -> dict[str, str]:
        """
        Construct a single episode entry.

        The title is sanitized and spaces are replaced with underscores so the
        resulting name is safe to use as a filename or URL segment.
        """
        anime_id         = anime["id"]
        sanitized_title  = sanitize_filename(anime["title"]["english"]).replace(" ", "_")
        name             = f"{anime_id}_{sanitized_title}_episode_{episode}_{content_type}"
        url              = f"{PROVIDER}/{anime_id}/{episode}/{content_type}"
        return {"name": name, "url": url}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> Tuple[List[dict[str, str]], str]:
        """
        Generate all sub/dub episode entries for every anime in the list.

        Skips any anime whose episode count is falsy (None, 0, empty string).

        Returns
        -------
        entries         : Flat list of ``{"name": ..., "url": ...}`` dicts.
        PROVIDER_ORIGIN : Base origin URL of the streaming provider.
        """
        entries: List[dict[str, str]] = []

        for anime in self.anime_list:
            if not anime["episodes"]:
                continue

            for episode in range(1, int(anime["episodes"]) + 1):
                for content_type in CONTENT_TYPES:
                    entries.append(self._build_episode_entry(anime, episode, content_type))

        return entries, PROVIDER_ORIGIN

    def origin(self) -> str:
        """Return the base origin URL of the streaming provider."""
        return PROVIDER_ORIGIN