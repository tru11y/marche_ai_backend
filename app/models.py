from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime
from .database import Base

class ProductDB(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Integer)
    description = Column(String)
    image_url = Column(String, nullable=True)
    in_stock = Column(Boolean, default=True)

class OrderDB(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    customer_phone = Column(String)
    product_name = Column(String)
    customer_name = Column(String)
    delivery_location = Column(String)
    amount = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="EN_ATTENTE_CAUTION")

class MessageDB(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, index=True)
    role = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)