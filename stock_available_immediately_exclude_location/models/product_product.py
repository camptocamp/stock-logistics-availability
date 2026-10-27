# Copyright 2023 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import ormcache


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _compute_available_quantities_dict(self):
        # OVERRIDE: deduce the quantity in the excluded locations from the
        # immediately usable quantity.
        res, stock_dict = super()._compute_available_quantities_dict()
        excluded_qty_dict = (
            self._get_qty_available_in_locations_excluded_from_immediately_usable_qty()
        )
        for product_id, qty in excluded_qty_dict.items():
            res[product_id]["immediately_usable_qty"] -= qty
        return res, stock_dict

    def _get_qty_available_in_locations_excluded_from_immediately_usable_qty(self):
        """Return the quantity available in the excluded locations, by product.

        If no location is excluded, return an empty dict.
        """
        exclude_location_ids = (
            self._get_location_ids_excluded_from_immediately_usable_qty()
        )
        if not exclude_location_ids:
            return {}

        context = self.env.context
        to_date = context.get("to_date")
        to_date = fields.Datetime.to_datetime(to_date)
        dates_in_the_past = False
        if to_date and to_date < fields.Datetime.now():
            dates_in_the_past = True

        # we use strict=True to avoid time consuming query criteria on location
        # to get children locations of the excluded locations. The method
        # _get_location_ids_excluded_from_immediately_usable_qty has already
        # resolved the children locations of the excluded locations.
        products_with_excluded_loc = self.with_context(
            location=list(exclude_location_ids), strict=True
        )

        if dates_in_the_past:
            # we call the original _compute_quantities_dict since
            # the qty_available will be computed from quants and
            # moves
            excluded_qty_dict = products_with_excluded_loc._compute_quantities_dict(
                context.get("lot_id"),
                context.get("owner_id"),
                context.get("package_id"),
                context.get("from_date"),
                to_date,
            )
            return {p: q["qty_available"] for p, q in excluded_qty_dict.items()}
        # we are not in the past, the qty available is the sum of quant's qties
        # into the excluded locations. A simple read_group will do the job.
        # By avoiding the call to _compute_quantities_dict, we avoid 2 useless
        # queries to the database to retrieve the incoming and outgoing moves
        # that are not needed here and therefore improve the performance.
        (
            domain_quant_loc,
            _domain_move_in_loc,
            _domain_move_out_loc,
        ) = products_with_excluded_loc._get_domain_locations()
        domain_quant = Domain("product_id", "in", self.ids) & domain_quant_loc
        quant = self.env["stock.quant"].with_context(active_test=False)
        return {
            product.id: quantity
            for product, quantity in quant._read_group(
                domain_quant,
                ["product_id"],
                ["quantity:sum"],
            )
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
