from ...extensions.manager import ExtensionsManager, get_extensions_manager
from ...product.models import Product


def get_product_tax_rate(product: Product, manager: ExtensionsManager = None) -> str:
    manager = manager or get_extensions_manager()
    tax_rate = manager.get_tax_code_from_object_meta(product).code
    return tax_rate
