def buscar_pecas_disponiveis(product_model):
    return (
        product_model.query
        .filter_by(category='Peça', active=True)
        .order_by(product_model.name)
        .all()
    )


def buscar_pecas_por_classe(product_model, slots):
    return {
        slot_key: (
            product_model.query
            .filter_by(category='Peça', component_class=slot_key, active=True)
            .order_by(product_model.name)
            .all()
        )
        for slot_key, _, _ in slots
    }
