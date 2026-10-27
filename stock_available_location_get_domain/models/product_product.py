# Copyright 2023 ACSONE SA/NV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.fields import Domain


def _location_condition(condition):
    """Return the condition of a quant domain as a condition on its location.

    The conditions on other fields of the quant do not restrict the locations
    holding the quants, so they are dropped.
    """
    field_expr = condition.field_expr
    if field_expr == "location_id":
        if condition.operator == "any":
            return Domain(condition.value)
        if condition.operator == "not any":
            return ~Domain(condition.value)
        return Domain("id", condition.operator, condition.value)
    if field_expr.startswith("location_id."):
        return Domain(
            field_expr.removeprefix("location_id."),
            condition.operator,
            condition.value,
        )
    return Domain.TRUE


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _get_domain_location_for_locations(self):
        """
        Adapt the domain computed for stock.quant for stock.location
        """
        quant_domain = self._get_domain_locations()[0]
        return Domain(quant_domain).map_conditions(_location_condition)
