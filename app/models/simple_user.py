from sqlalchemy import Integer, String, Float
from sqlalchemy.orm import mapped_column, Mapped
from app.database import Base

class SimpleUser(Base):
    __tablename__ = "simple_user"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="Usuario")
    money: Mapped[float] = mapped_column(Float, nullable=False)