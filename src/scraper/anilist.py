import aiohttp
from pathvalidate import sanitize_filename
from .config import PROVIDER

# GraphQL query to fetch popular anime with episode counts from AniList
ANILIST_QUERY = """
    query ($page: Int, $perPage: Int) {
        Page(page: $page, perPage: $perPage) {
            media(type: ANIME, sort: POPULARITY_DESC) {
                id
                title { english }
                episodes
            }
        }
    }
"""

ANILIST_API_URL = "https://graphql.anilist.co"
CONTENT_TYPES = ["sub", "dub"]


class AnilistGenerator:
    """Generates a list of anime episode entries from AniList's most popular titles."""

    def __init__(self, page: int, units: int) -> None:
        self.page = page
        self.units = units

    async def generate(self) -> list[dict]:
        """
        Fetches anime from AniList and returns a flat list of episode entries,
        each with a sanitized name and provider URL for both sub and dub.
        Returns an empty list on failure.
        """
        variables = {"page": self.page, "perPage": self.units}

        async with aiohttp.ClientSession() as session:
            try:
                response = await session.post(
                    ANILIST_API_URL,
                    json={"query": ANILIST_QUERY, "variables": variables},
                    headers={"Content-Type": "application/json"},
                )
                data = await response.json()
                anime_list = data["data"]["Page"]["media"]

                return [
                    self._build_episode_entry(anime, episode, content_type)
                    for anime in anime_list
                    if anime["episodes"]
                    for episode in range(1, int(anime["episodes"]) + 1)
                    for content_type in CONTENT_TYPES
                ]

            except Exception:
                return []

    def _build_episode_entry(self, anime: dict, episode: int, content_type: str) -> dict:
        """Constructs a single episode entry with a sanitized name and provider URL."""
        anime_id = anime["id"]
        sanitized_title = sanitize_filename(anime["title"]["english"]).replace(" ", "_")
        name = f"{anime_id}_{sanitized_title}_episode_{episode}_{content_type}"
        url = f"{PROVIDER}/ani/{anime_id}/{episode}/{content_type}"
        return {"name": name, "url": url}