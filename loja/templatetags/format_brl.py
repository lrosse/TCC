# Filtros de formatação pt-BR para moeda e inteiros
# Uso:
#   {{ valor|brl }}            -> "1.234,56"
#   {{ valor|brl_currency }}   -> "R$ 1.234,56"
#   {{ inteiro|milhar }}       -> "12.345"
# ----------------------------------------------------------
from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

def _format_brl(value, casas=2):
    """
    Formata Decimal/float/str como pt-BR:
    - separador decimal = ','
    - separador de milhar = '.'
    - arredonda para 'casas' (padrão 2)
    """
    try:
        val = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return "0,00"

    # garante o número de casas
    q = Decimal(10) ** -casas
    val = val.quantize(q)

    # formata em estilo "en_US" e depois troca separadores
    # ex: 12345.6 -> "12,345.60" -> "12.345,60"
    s = f"{val:,.{casas}f}"   # usa vírgula para milhar e ponto para decimal
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s

@register.filter(name="brl")
def brl(value):
    """Somente número formatado (ex: 1.234,56)."""
    return _format_brl(value)

@register.filter(name="brl_currency")
def brl_currency(value):
    """Número com 'R$ ' (ex: R$ 1.234,56)."""
    return f"R$ {_format_brl(value)}"

@register.filter(name="milhar")
def milhar(value):
    """Inteiro com separador de milhar (ex: 12.345)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "0"
    return f"{n:,}".replace(",", ".")