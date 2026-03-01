from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, Optional, TypeVar

from flask_sqlalchemy.model import Model

T = TypeVar('T', bound=Model)


class GenericCrudService(Generic[T]):
    """Serviço CRUD genérico para modelos SQLAlchemy."""
    def __init__(self, model: type[T], db):
        """Configura o serviço com o modelo e instância de banco."""
        self.model = model
        self.db = db

    def get_active(self):
        """Retorna entidades ativas quando o campo `active` existir."""
        query = self.model.query
        if hasattr(self.model, 'active'):
            query = query.filter_by(active=True)
        return query.all()

    def get_by_id(self, entity_id: int) -> Optional[T]:
        """Busca uma entidade pelo identificador primário."""
        return self.model.query.get(entity_id)

    def create(self, **kwargs) -> T:
        """Cria e adiciona uma nova entidade à sessão do banco."""
        entity = self.model(**kwargs)
        self.db.session.add(entity)
        return entity

    def update(self, entity: T, **kwargs) -> T:
        """Atualiza atributos de uma entidade existente."""
        for key, value in kwargs.items():
            setattr(entity, key, value)
        return entity

    def soft_delete(self, entity: T):
        """Desativa a entidade quando possível ou remove da sessão."""
        if hasattr(entity, 'active'):
            entity.active = False
        else:
            self.db.session.delete(entity)


@dataclass
class ProductDTO:
    """DTO com dados e validações básicas de produto."""
    name: str
    category: str
    stock: int
    price: Decimal
    cost_price: Decimal
    component_class: Optional[str] = None
    serial_number: Optional[str] = None

    def validate(self):
        """Valida campos obrigatórios e valores monetários/estoque."""
        if not self.name.strip():
            raise ValueError('Nome do produto é obrigatório.')
        if self.stock < 0:
            raise ValueError('Estoque não pode ser negativo.')
        if self.price < 0 or self.cost_price < 0:
            raise ValueError('Valores monetários não podem ser negativos.')


@dataclass
class ClientDTO:
    """DTO com dados e validações básicas de cliente."""
    name: str
    cpf: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    def validate(self):
        """Valida os campos obrigatórios de cliente."""
        if not self.name.strip():
            raise ValueError('Nome do cliente é obrigatório.')
