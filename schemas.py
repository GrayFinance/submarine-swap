from pydantic import BaseModel, PositiveInt

class SubmarineSwapSchema(BaseModel):
    pubkey: str
    value: PositiveInt
    payment_hash: str
