from pydantic import BaseModel

class UserCreate(BaseModel):
    name: str
    money: float
    
class UserOut(UserCreate):
    id: int
    