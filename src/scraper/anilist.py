import aiohttp
from typing import List


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


class AnilistGenerator:
    """Generates a list of anime episode entries from AniList's most popular titles."""

    def __init__(self, page: int, units: int) -> None:
        self.page = page
        self.units = units

    async def generate(self) -> List[dict]:
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

                return anime_list

            except Exception:
                return []