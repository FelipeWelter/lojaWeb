from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, Optional, TypeVar

from flask_sqlalchemy.model import Model

T = TypeVar('T', bound=Model)


class GenericCrudService(Generic[T]):
    def __init__(self, model: type[T], db):
        self.model = model
        self.db = db

    def get_active(self):
        query = self.model.query
        if hasattr(self.model, 'active'):
            query = query.filter_by(active=True)
        return query.all()

    def get_by_id(self, entity_id: int) -> Optional[T]:
        return self.model.query.get(entity_id)

    def create(self, **kwargs) -> T:
        entity = self.model(**kwargs)
        self.db.session.add(entity)
        return entity

    def update(self, entity: T, **kwargs) -> T:
        for key, value in kwargs.items():
            setattr(entity, key, value)
        return entity

    def soft_delete(self, entity: T):
        if hasattr(entity, 'active'):
            entity.active = False
        else:
            self.db.session.delete(entity)


@dataclass
class ProductDTO:
    name: str
    category: str
    stock: int
    price: Decimal
    cost_price: Decimal
    component_class: Optional[str] = None
    serial_number: Optional[str] = None

    def validate(self):
        if not self.name.strip():
            raise ValueError('Nome do produto é obrigatório.')
        if self.stock < 0:
            raise ValueError('Estoque não pode ser negativo.')
        if self.price < 0 or self.cost_price < 0:
            raise ValueError('Valores monetários não podem ser negativos.')


@dataclass
class ClientDTO:
    name: str
    cpf: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    def validate(self):
        if not self.name.strip():
            raise ValueError('Nome do cliente é obrigatório.')
