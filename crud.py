from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, Optional, TypeVar

from flask_sqlalchemy.model import Model

T = TypeVar('T', bound=Model)


class GenericCrudService(Generic[T]):
    """Classe `GenericCrudService`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
    def __init__(self, model: type[T], db):
        """Função `__init__`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
        self.model = model
        self.db = db

    def get_active(self):
        """Função `get_active`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
        query = self.model.query
        if hasattr(self.model, 'active'):
            query = query.filter_by(active=True)
        return query.all()

    def get_by_id(self, entity_id: int) -> Optional[T]:
        """Função `get_by_id`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
        return self.model.query.get(entity_id)

    def create(self, **kwargs) -> T:
        """Função `create`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
        entity = self.model(**kwargs)
        self.db.session.add(entity)
        return entity

    def update(self, entity: T, **kwargs) -> T:
        """Função `update`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
        for key, value in kwargs.items():
            setattr(entity, key, value)
        return entity

    def soft_delete(self, entity: T):
        """Função `soft_delete`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
        if hasattr(entity, 'active'):
            entity.active = False
        else:
            self.db.session.delete(entity)


@dataclass
class ProductDTO:
    """Classe `ProductDTO`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
    name: str
    category: str
    stock: int
    price: Decimal
    cost_price: Decimal
    component_class: Optional[str] = None
    serial_number: Optional[str] = None

    def validate(self):
        """Função `validate`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
        if not self.name.strip():
            raise ValueError('Nome do produto é obrigatório.')
        if self.stock < 0:
            raise ValueError('Estoque não pode ser negativo.')
        if self.price < 0 or self.cost_price < 0:
            raise ValueError('Valores monetários não podem ser negativos.')


@dataclass
class ClientDTO:
    """Classe `ClientDTO`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
    name: str
    cpf: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    def validate(self):
        """Função `validate`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
        if not self.name.strip():
            raise ValueError('Nome do cliente é obrigatório.')
