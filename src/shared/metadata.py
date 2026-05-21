from pydantic import BaseModel


class Metadata(BaseModel):
    '''Default class for metadata shared between processes using pydantic.
    Always serialize and deserialize before sharing between processes.
    '''
    video: str = ""
    parts: int = 0
    subtitles: list[str] = []
    dir: str = ""
