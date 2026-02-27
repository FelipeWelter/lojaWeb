from decimal import Decimal


def calcular_margem_lucro(custo, venda):
    """Função `calcular_margem_lucro`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
    custo_dec = Decimal(custo or 0)
    venda_dec = Decimal(venda or 0)
    if venda_dec <= 0:
        return Decimal('0.00')
    margem = ((venda_dec - custo_dec) / venda_dec) * Decimal('100')
    return margem.quantize(Decimal('0.01'))


def calcular_preco_sugerido(custo_total, markup=Decimal('0.20')):
    """Função `calcular_preco_sugerido`: explica o objetivo deste bloco para facilitar alterações e colaboração."""
    custo_dec = Decimal(custo_total or 0)
    return (custo_dec * (Decimal('1.00') + Decimal(markup))).quantize(Decimal('0.01'))
