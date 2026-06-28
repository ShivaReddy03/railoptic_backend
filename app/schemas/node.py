from pydantic import BaseModel


class NodeOut(BaseModel):
    id: str
    line: str
    gps: dict
    status: str
    health: int

    class Config:
        alias_generator = lambda string: string
        validate_by_name = True
