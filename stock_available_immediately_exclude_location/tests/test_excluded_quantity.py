# Copyright 2026 Camptocamp SA (https://www.camptocamp.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields
from odoo.tests.common import TransactionCase


class TestExcludedQuantity(TransactionCase):
    """What an excluded location contributes to the immediately usable quantity.

    The immediately usable quantity is the quantity on hand, minus the outgoing
    and expired quantities. For an excluded location, exactly what it
    contributes to that quantity must be deduced, under the same conditions
    (date, lot...) as the quantity itself.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.excluded_location = cls.env["stock.location"].create(
            {
                "name": "Excluded Location",
                "location_id": cls.warehouse.view_location_id.id,
                "usage": "internal",
                "exclude_from_immediately_usable_qty": True,
            }
        )
        cls.supplier_location = cls.env.ref("stock.stock_location_suppliers")
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.product = cls.env["product.product"].create(
            {"name": "Product Test", "type": "consu", "is_storable": True}
        )

    def _receive(self, location, qty):
        move = self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": qty,
                "location_id": self.supplier_location.id,
                "location_dest_id": location.id,
            }
        )
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.write({"quantity": qty, "picked": True})
        move._action_done()

    def _get_immediately_usable_qty(self, product, **context):
        return product.with_context(
            warehouse_id=self.warehouse.id, **context
        ).immediately_usable_qty

    def test_delivery_reserved_in_excluded_location(self):
        """A delivery reserved in an excluded location is not deduced twice.

        The delivery is outgoing, so it is already deduced from the quantity on
        hand. The goods it takes from the excluded location must not be deduced
        a second time as goods of the excluded location.

        Scenario:
            1. Have 10 units in stock and 5 units in the excluded location.
            2. Confirm a delivery of 5 units, reserved in the excluded location.
        Expected:
            - The 10 units in stock are still immediately usable.
        """
        quant_model = self.env["stock.quant"]
        quant_model._update_available_quantity(self.product, self.stock_location, 10)
        quant_model._update_available_quantity(self.product, self.excluded_location, 5)
        self.assertEqual(self._get_immediately_usable_qty(self.product), 10)
        delivery = self.env["stock.move"].create(
            {
                "product_id": self.product.id,
                "product_uom_qty": 5,
                "location_id": self.excluded_location.id,
                "location_dest_id": self.customer_location.id,
            }
        )
        delivery._action_confirm()
        delivery._action_assign()
        self.assertEqual(delivery.state, "assigned")
        self.assertEqual(self._get_immediately_usable_qty(self.product), 10)

    def test_date_without_time(self):
        """A date without time covers the whole day, for the excluded locations too.

        Odoo reads a date without time as the end of that day, so the goods
        received today are on hand at today's date. The goods received today in
        the excluded location must be deduced at today's date as well.

        Scenario:
            1. Receive 10 units in stock and 5 units in the excluded location,
               today.
            2. Get the immediately usable quantity at today's date, without time.
        Expected:
            - Only the 10 units in stock are immediately usable.
        """
        self._receive(self.stock_location, 10)
        self._receive(self.excluded_location, 5)
        today = fields.Date.to_string(fields.Date.today())
        self.assertEqual(
            self._get_immediately_usable_qty(self.product, to_date=today), 10
        )

    def test_lot_in_context(self):
        """Only the goods of the lot asked for are deduced.

        Scenario:
            1. Have 10 units of lot A in stock, and 5 units of lot B in the
               excluded location.
            2. Get the immediately usable quantity of lot A.
        Expected:
            - The 10 units of lot A are immediately usable: the goods of lot B
              in the excluded location are not deduced from them.
        """
        product = self.env["product.product"].create(
            {
                "name": "Lot Product Test",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        lot_a, lot_b = self.env["stock.lot"].create(
            [
                {"name": "Lot A", "product_id": product.id},
                {"name": "Lot B", "product_id": product.id},
            ]
        )
        quant_model = self.env["stock.quant"]
        quant_model._update_available_quantity(
            product, self.stock_location, 10, lot_id=lot_a
        )
        quant_model._update_available_quantity(
            product, self.excluded_location, 5, lot_id=lot_b
        )
        self.assertEqual(self._get_immediately_usable_qty(product, lot_id=lot_a.id), 10)
