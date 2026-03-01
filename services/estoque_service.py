def buscar_pecas_disponiveis(product_model):
    """Busca peças e computadores ativos com estoque disponível."""
    return (
        product_model.query
        .filter(
            product_model.active.is_(True),
            product_model.stock > 0,
            product_model.category.in_(['Peça', 'Computador']),
        )
        .order_by(product_model.name)
        .all()
    )


def buscar_pecas_por_classe(product_model, slots):
    """Agrupa peças ativas por classe de componente para cada slot."""
    return {
        slot_key: (
            product_model.query
            .filter_by(category='Peça', component_class=slot_key, active=True)
            .order_by(product_model.name)
            .all()
        )
        for slot_key, _, _ in slots
    }
