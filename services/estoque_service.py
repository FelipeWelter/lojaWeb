def buscar_pecas_disponiveis(product_model):
    """Função `buscar_pecas_disponiveis`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
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
    """Função `buscar_pecas_por_classe`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
    return {
        slot_key: (
            product_model.query
            .filter_by(category='Peça', component_class=slot_key, active=True)
            .order_by(product_model.name)
            .all()
        )
        for slot_key, _, _ in slots
    }
