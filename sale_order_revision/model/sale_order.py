# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2013 Agile Business Group sagl (<http://www.agilebg.com>)
#    @author Lorenzo Battistini <lorenzo.battistini@agilebg.com>
#    @author Raphaël Valyi <raphael.valyi@akretion.com> (ported to sale from
#    original purchase_order_revision by Lorenzo Battistini)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import fields, models, api
from openerp.tools.translate import _
import logging

_logger = logging.getLogger(__name__)


class sale_order(models.Model):
    _inherit = "sale.order"
    current_revision_id = fields.Many2one('sale.order',
                                          'Current revision',
                                          readonly=True,
                                          copy=True)
    old_revision_ids = fields.One2many('sale.order',
                                       'current_revision_id',
                                       'Old revisions',
                                       readonly=True,
                                       context={'active_test': False})
    revision_number = fields.Integer('Revision',
                                     copy=False)
    unrevisioned_name = fields.Char('Order Reference',
                                    copy=True,
                                    readonly=False)
    active = fields.Boolean('Active',
                            default=True,
                            copy=True)

    _sql_constraints = [
        ('revision_unique',
         'unique(unrevisioned_name, revision_number, company_id)',
         'Order Reference and revision must be unique per Company.'),
    ]

    @api.multi
    def copy_quotation(self):
        _logger.info("in copy quotation")
        self.ensure_one()

        # save existing procurement group id and remove it for new revision
        procurement_group_id = self.procurement_group_id.id
        self.write({'procurement_group_id': None})

        revision_self = self.with_context(new_sale_revision=True)
        action = super(sale_order, revision_self).copy_quotation()
        old_revision = self.browse(action['res_id'])
        action['res_id'] = self.id
        self.delete_workflow()
        self.create_workflow()
        self.write({'state': 'draft'})
        msg = _('New revision created: %s') % self.name
        self.message_post(body=msg)
        old_revision.message_post(body=msg)

        # put existing procurement group id on old order
        old_revision.write({'procurement_group_id': procurement_group_id})
        self.write({'procurement_group_id': None})

        # swap order lines of old and new order
        old_line_ids = [line.id for line in old_revision.order_line]
        new_line_ids = [line.id for line in self.order_line]
        so_line = self.pool.get('sale.order.line')
        so_line.write(self._cr, self._uid, old_line_ids,
                      {'order_id': self.id}, context=self._context)
        so_line.write(self._cr, self._uid, new_line_ids,
                      {'order_id': old_revision.id}, context=self._context)

        return action

    @api.returns('self', lambda value: value.id)
    @api.multi
    def copy(self, defaults=None):
        if not defaults:
            defaults = {}
        if self.env.context.get('new_sale_revision'):
            # Create a revision of the sale order
            prev_name = self.name
            revno = self.revision_number
            _logger.info("current revision number: %d", revno)
            self.write({'revision_number': revno + 1,
                        'name': '%s-%02d' % (self.unrevisioned_name,
                                             revno + 1)
                        })
            defaults.update({'name': prev_name,
                             'revision_number': revno,
                             'active': False,
                             'state': 'cancel',
                             'current_revision_id': self.id,
                             })
        return super(sale_order, self).copy(defaults)

    @api.model
    def create(self, values):
        if 'unrevisioned_name' not in values:
            if values.get('name', '/') == '/':
                seq = self.env['ir.sequence']
                values['name'] = seq.next_by_code('sale.order') or '/'
            values['unrevisioned_name'] = values['name']
        return super(sale_order, self).create(values)
