# Copyright NuoBiT Solutions, S.L. (<https://www.nuobit.com>)
# Eric Antones <eantones@nuobit.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import models, api, _


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def check_lines(self, pos_config_id, lines):
        # group lines
        grouped_lines = {}
        for i, l in enumerate(lines, 1):
            product = self.env['product.product'].browse(l['product_id'])
            if product.tracking == 'none':
                if l['lot_name']:
                    return {'msg': _("Line %i - Configuration error: A product without tracking (%s) "
                                     "cannot have lots or serial numbers %s") % (
                                       i, product.display_name, l['lot_name'])}
                key = (product.id, None)
                if key in grouped_lines:
                    grouped_lines[key]['quantity'] += l['quantity']
                else:
                    grouped_lines[key] = {
                        'product': product,
                        'tracking': None,
                        'quantity': l['quantity'],
                    }
            else:
                if not l['lot_name']:
                    return {'msg': _("Line %i - Data integrity Error: A product with tracking (%s) "
                                     "must have a lot or serial number") % (
                                       i, product.display_name,)}

                if product.tracking == 'lot':
                    if len(l['lot_name']) > 1:
                        return {'msg': _("Line %i - Data integrity Error: A product with lot tracking (%s) "
                                         "must have only one lot assigned %s") % (
                                           i, product.display_name, l['lot_name'])}
                    lot_name = l['lot_name'][0]
                    lot = self.env['stock.production.lot'].search([
                        ('product_id', '=', product.id),
                        ('name', '=', lot_name),
                    ])
                    if not lot:
                        return {'msg': _("Line %i - Lot number '%s' does not exist "
                                         "for the product %s") % (
                                           i, lot_name, product.display_name)}

                    key = (product.id, lot.id)
                    if key in grouped_lines:
                        grouped_lines[key]['quantity'] += l['quantity']
                    else:
                        grouped_lines[key] = {
                            'product': product,
                            'tracking': lot,
                            'quantity': l['quantity'],
                        }
                else:
                    if len(l['lot_name']) != l['quantity']:
                        return {'msg': _("Line %i - Data integrity Error: A product with serial number tracking (%s) "
                                         "must have as many serial numbers as quantity (%s), found %s") % (
                                           i, product.display_name, l['quantity'], l['lot_name'])}
                    for serial_name in l['lot_name']:
                        lot = self.env['stock.production.lot'].search([
                            ('product_id', '=', product.id),
                            ('name', '=', serial_name),
                        ])
                        if not lot:
                            return {'msg': _("Line %i - Serial number '%s' does not exist "
                                             "for the product %s") % (
                                               i, serial_name, product.display_name)}

                        key = (product.id, lot.id)
                        if key in grouped_lines:
                            return {'msg': _("Line %i - The product '%s' already exists in "
                                             "another line with the same serial number (%s).") % (
                                               i, product.display_name, serial_name)}
                        else:
                            grouped_lines[key] = {
                                'product': product,
                                'tracking': lot,
                                'quantity': 1,
                            }

        # checks
        location = self.env['pos.config'].browse(pos_config_id).stock_location_id
        quants_loc_domain = [('location_id', '=', location.id)]
        for l in filter(lambda x: x['quantity'] > 0, grouped_lines.values()):
            product = l['product']
            quants_domain = quants_loc_domain + [('product_id', '=', product.id)]
            lot, lot_msg = l['tracking'], None
            if product.tracking != 'none':
                quants_domain += [('lot_id', '=', lot.id)]
                lot_msg = ' (%s)' % lot.name
            quants = self.env['stock.quant'].search(quants_domain)
            if not quants:
                return {'msg': _("The product '%s'%s has no stock") % (
                    product.display_name, lot_msg or '')}
            elif len(quants) > 1:
                return {'msg': _("Data integrity Error: The product '%s'%s has more "
                                 "than one match in the stock table") % (product.display_name, lot_msg or '')}
            quantity_available = quants.quantity - quants.reserved_quantity
            if l['quantity'] > quantity_available:
                if quants.quantity < 0:
                    return {'msg': _("The product '%s'%s has negative stock %s") % (
                        product.display_name, lot_msg or '', quants.quantity)}
                else:
                    if l['quantity'] <= quants.quantity:
                        return {'msg': _("The product '%s'%s has not enough stock available: %s "
                                         "because there's %s units reserved.") % (
                                           product.display_name, lot_msg or '',
                                           quantity_available, quants.reserved_quantity)}
                    else:
                        return {'msg': _("The product '%s'%s has not enough stock. Available: %s") % (
                            product.display_name, lot_msg or '', quantity_available)}

        return None
