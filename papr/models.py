from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Table, Column, Integer, String

Base = declarative_base()


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    identifier = Column(String(50))
    full_name = Column(String(100))

    def print_stuff(self):
        print(f"{self.identifier} - {self.full_name}")
