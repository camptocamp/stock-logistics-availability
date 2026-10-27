# Copyright 2023 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, models
from odoo.fields import Domain
from odoo.tools import ormcache


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _compute_available_quantities_dict(self):
        # OVERRIDE: deduce what the excluded locations contribute to the
        # immediately usable quantity.
        res, stock_dict = super()._compute_available_quantities_dict()
        excluded_qty_dict = self._get_immediately_usable_qty_in_excluded_locations()
        for product_id, qty in excluded_qty_dict.items():
            res[product_id]["immediately_usable_qty"] -= qty
        return res, stock_dict

    def _get_immediately_usable_qty_in_excluded_locations(self):
        """Return the immediately usable quantity in the excluded locations.

        It is computed by the same methods as the immediately usable quantity
        itself, only on the excluded locations, so that exactly what they
        contribute to it is deduced: the outgoing and expired quantities, and
        the date, lot, owner and package of the context are taken into account
        the same way. If no location is excluded, return an empty dict.
        """
        exclude_location_ids = (
            self._get_location_ids_excluded_from_immediately_usable_qty()
        )
        if not exclude_location_ids:
            return {}
        # ``strict`` avoids looking for the children of the excluded locations:
        # those of the excluded view locations are already among them.
        products = self.with_context(location=list(exclude_location_ids), strict=True)
        excluded_res, _stock_dict = super(
            ProductProduct, products
        )._compute_available_quantities_dict()
        return {
            product_id: quantities["immediately_usable_qty"]
            for product_id, quantities in excluded_res.items()
        }

    @api.model
    @ormcache(
        "tuple(self.env.companies.ids)",
        "str(self.env.context.get('location'))",
        "str(self.env.context.get('search_location'))",
        "str(self.env.context.get('warehouse_id'))",
        "str(self.env.context.get('search_warehouse'))",
    )
    def _get_location_ids_excluded_from_immediately_usable_qty(self):
        """Return the ids of the locations excluded from the immediately usable qty.

        These are the excluded leaf locations, and the children of the excluded
        view locations.
        """
        locations = self._get_locations_excluded_from_immediately_usable_qty()
        view_locations = locations.filtered(lambda location: location.usage == "view")
        # we must exclude the children of the view locations
        locations |= self.env["stock.location"].search(
            [
                ("location_id", "child_of", view_locations.ids),
                ("usage", "in", ["internal", "transit"]),
            ]
        )
        return tuple(locations.ids)

    @api.model
    def _get_locations_excluded_from_immediately_usable_qty(self):
        return self.env["stock.location"].search(
            self._get_domain_location_excluded_from_immediately_usable_qty()
        )

    @api.model
    def _get_domain_location_excluded_from_immediately_usable_qty(self):
        """Return the domain of the excluded locations in the scope of the context."""
        # The quant domain restricts ``location_id`` to the locations of the
        # context: apply the same restriction to the locations themselves.
        quant_domain = self.env["product.product"]._get_domain_locations()[0]
        location_domain = Domain(quant_domain).map_conditions(
            lambda condition: Domain("id", condition.operator, condition.value)
            if condition.field_expr == "location_id"
            else condition
        )
        return location_domain & Domain(
            "exclude_from_immediately_usable_qty", "=", True
        )
