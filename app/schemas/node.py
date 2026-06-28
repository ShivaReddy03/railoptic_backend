from pydantic import BaseModel


class NodeOut(BaseModel):
    id: str
    line: str
    gps: dict
    status: str
    health: int

    class Config:
        alias_generator = lambda string: string
        allow_population_by_field_name = True
