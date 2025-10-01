from django import template

register = template.Library()

@register.filter
def estoque_format(qtd):
    """
    Formata a quantidade de estoque:
    - < 50 => 'Apenas X unidades'
    - 50 <= qtd < 500 => '+N disponíveis' (múltiplos de 50)
    - >= 500 => '+500 unidades'
    """
    try:
        qtd = int(qtd)
    except (ValueError, TypeError):
        return ""

    if qtd < 50:
        return f"Apenas {qtd} unidade{'s' if qtd > 1 else ''}"
    elif qtd < 500:
        agrupado = (qtd // 50) * 50
        return f"+{agrupado} disponíveis"
    else:
        return "+500 disponíveis"
