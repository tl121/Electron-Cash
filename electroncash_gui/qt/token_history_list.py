#!/usr/bin/env python3
#
# Electron Cash - lightweight Bitcoin Cash client
# Copyright (C) 2022 The Electron Cash Developers
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from enum import IntEnum
from typing import Optional

from PyQt5 import QtCore
from PyQt5.QtGui import QBrush, QColor, QIcon, QFont
from PyQt5.QtWidgets import QMenu, QHeaderView

from electroncash import token
from electroncash.i18n import _, ngettext
from electroncash.util import profiler, PrintError

from .token_list import TokenList
from .token_meta import TokenMetaQt
from .util import MONOSPACE_FONT, MyTreeWidget, rate_limited, SortableTreeWidgetItem


class TokenHistoryList(MyTreeWidget, PrintError):

    class Col(IntEnum):
        """Column numbers. This is to make code in on_update easier to read.
        If you modify these, make sure to modify the column header names in
        the MyTreeWidget constructor."""
        status = 1
        date = 2
        description = 3
        category_id = 4
        fungible_amount = 5
        nft_amount = 6
        fungible_balance = 7
        nft_balance = 8

    class DataRoles(IntEnum):
        """Data roles. Again, to make code in on_update easier to read."""
        tx_hash = QtCore.Qt.UserRole  # This must be this value so that superclass on_edited() picks up the label change
        status = QtCore.Qt.UserRole + 1
        category = QtCore.Qt.UserRole + 2
        outpoint = QtCore.Qt.UserRole + 3
        nft_row = QtCore.Qt.UserRole + 4
        commitment = QtCore.Qt.UserRole + 5
        capability = QtCore.Qt.UserRole + 6
        editable_label = QtCore.Qt.UserRole + 7
        item_key = QtCore.Qt.UserRole + 8

    statusIcons = {}

    def __init__(self, parent=None):
        MyTreeWidget.__init__(self, parent, self.create_menu, [], self.Col.description, deferred_updates=True)
        PrintError.__init__(self)

        headers = ['', '', _('Date'), _('Description'), _('Category ID'), _('Fungible Amount'), _('NFT Amount'),
                   _("Fungible Balance"), _("NFT Balance")]
        self.update_headers(headers)
        self.setColumnHidden(1, True)
        self.setSortingEnabled(True)
        self.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.wallet = self.parent.wallet
        self.cleaned_up = False
        self.monospaceFont = QFont(MONOSPACE_FONT)
        self.monospaceFontCondensed = QFont(MONOSPACE_FONT)
        self.monospaceFontCondensed.setStretch(QFont.SemiCondensed)
        self.withdrawalBrush = QBrush(QColor("#BC1E1E"))
        self.batonIcon = QIcon(":icons/baton.png")
        self.mutableIcon = QIcon(":icons/mutable.png")
        self.mintingMutableIcon = QIcon(":icons/minting-mutable.png")
        self.token_meta: TokenMetaQt = parent.token_meta
        self.setTextElideMode(QtCore.Qt.ElideMiddle)
        for col in range(self.Col.category_id, len(headers)):
            self.header().setSectionResizeMode(col, QHeaderView.Interactive)
        self.header().setSectionResizeMode(self.Col.description, QHeaderView.Stretch)
        for col in range(self.Col.fungible_amount, len(headers)):
            self.header().resizeSection(col, 100)

    def clean_up(self):
        self.cleaned_up = True

    @rate_limited(1.0, classlevel=True, ts_after=True)
    def update(self):
        if self.cleaned_up:
            # short-cut return if window was closed and wallet is stopped
            return
        super().update()

    @profiler
    def on_update(self):
        def item_key(item: SortableTreeWidgetItem) -> str:
            return item.data(0, self.DataRoles.item_key) or ""
        # Remember selections and expanded top-level items (must be done before clear)
        selected_keys = {item_key(item) for item in self.selectedItems()}
        expanded_keys = {item_key(self.topLevelItem(i)) for i in range(self.topLevelItemCount())
                         if self.topLevelItem(i).childCount() > 0 and self.topLevelItem(i).isExpanded()}
        was_empty = self.topLevelItemCount() == 0

        self.clear()

        h = self.wallet.get_history(self.wallet.get_addresses(), reverse=True, receives_before_sends=True,
                                    include_tokens=True, include_tokens_balances=True)

        all_items = []
        for h_item in h:
            tx_hash, height, conf, timestamp, value, balance, tokens_deltas, tokens_balances = h_item
            if not tokens_deltas:
                continue
            label = self.wallet.get_label(tx_hash)
            status, status_str = self.wallet.get_tx_status(tx_hash, height, conf, timestamp)
            icon = self.parent.history_list.get_icon_for_status(status)

            for category_id, category_delta in tokens_deltas.items():
                tl_item_key = tx_hash + category_id
                fungible_amount = category_delta.get("fungibles", 0)
                cat_nfts_in = category_delta.get("nfts_in", [])
                cat_nfts_out = category_delta.get("nfts_out", [])
                bal_fts = tokens_balances.get(category_id, {}).get("fungibles", 0)
                bal_nfts = tokens_balances.get(category_id, {}).get("nfts", 0)
                nft_amount = len(cat_nfts_in) - len(cat_nfts_out)
                entry = ['', tx_hash, status_str, label, category_id, str(fungible_amount), str(nft_amount),
                         str(bal_fts), str(bal_nfts)]
                item = SortableTreeWidgetItem(entry)
                has_minting_ctr = 0
                has_mutable_ctr = 0
                item.setData(0, self.DataRoles.status, (status, conf))
                item.setData(0, self.DataRoles.tx_hash, tx_hash)
                item.setData(0, self.DataRoles.nft_row, False)
                item.setData(0, self.DataRoles.category, category_id)
                item.setData(0, self.DataRoles.editable_label, True)
                item.setData(0, self.DataRoles.item_key, tl_item_key)
                item.setToolTip(self.Col.category_id, category_id)
                item.setToolTip(self.Col.fungible_amount, str(fungible_amount))
                item.setToolTip(self.Col.nft_amount, str(nft_amount))
                item.setToolTip(self.Col.fungible_balance, str(bal_fts))
                item.setToolTip(self.Col.nft_balance, str(bal_nfts))
                item.setIcon(self.Col.category_id, self.token_meta.get_icon(category_id))
                if icon:
                    item.setIcon(0, icon)
                conf_suffix = ngettext("confirmation", "confirmations", conf)
                item.setToolTip(0, str(conf) + " " + conf_suffix)
                for col in (self.Col.category_id, self.Col.fungible_amount, self.Col.nft_amount,
                            self.Col.fungible_balance, self.Col.nft_balance):
                    item.setTextAlignment(col, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                    font = self.monospaceFont if col != self.Col.category_id else self.monospaceFontCondensed
                    item.setFont(col, font)
                item.setFont(self.Col.date, self.monospaceFont)
                if fungible_amount < 0 or nft_amount < 0:
                    item.setForeground(self.Col.description, self.withdrawalBrush)
                if fungible_amount < 0:
                    item.setForeground(self.Col.fungible_amount, self.withdrawalBrush)
                if nft_amount < 0:
                    item.setForeground(self.Col.nft_amount, self.withdrawalBrush)
                if bal_fts < 0:
                    item.setForeground(self.Col.fungible_balance, self.withdrawalBrush)
                if bal_nfts < 0:
                    item.setForeground(self.Col.nft_balance, self.withdrawalBrush)

                def add_nft(nft, out=False):
                    nonlocal has_minting_ctr, has_mutable_ctr
                    if out:
                        outpoint_hash, outpoint_n, token_data = nft
                    else:
                        outpoint_n, token_data = nft
                        outpoint_hash = tx_hash
                    outpoint_str = TokenList.get_outpoint_longname({"prevout_hash": outpoint_hash,
                                                                    "prevout_n": outpoint_n})
                    capability = token.get_nft_flag_text(token_data) or ""
                    direction = "-" if out else "+"
                    if token_data.is_immutable_nft():
                        capability = ""
                        direction = "   " + direction
                    commitment = token_data.commitment.hex()
                    capability_str = f"{capability} " if len(capability) else ""
                    commitment_str = f": {commitment}" if commitment else ""
                    name = f"{direction} {capability_str}NFT{commitment_str}"
                    nft_item = SortableTreeWidgetItem(['', tx_hash, '', name, '', '', '', '', '', ''])
                    nft_item.setFont(self.Col.description, self.monospaceFont)
                    nft_item.setData(0, self.DataRoles.nft_row, True)
                    nft_item.setData(0, self.DataRoles.outpoint, outpoint_str)
                    nft_item.setData(0, self.DataRoles.commitment, commitment)
                    nft_item.setData(0, self.DataRoles.capability, capability)
                    nft_item.setData(0, self.DataRoles.item_key, tl_item_key + outpoint_str)
                    if out:
                        nft_item.setForeground(self.Col.description, self.withdrawalBrush)
                    tt_suffix = ((": " + commitment_str) if commitment_str else "")
                    if token_data.is_minting_nft():
                        has_minting_ctr += 1
                        nft_item.setIcon(self.Col.description, self.batonIcon)
                        tt = _("Minting NFT") + tt_suffix
                    elif token_data.is_mutable_nft():
                        has_mutable_ctr += 1
                        nft_item.setIcon(self.Col.description, self.mutableIcon)
                        tt = _("Mutable NFT") + tt_suffix
                    else:
                        tt = _("NFT") + tt_suffix
                    nft_item.setToolTip(self.Col.description, tt)

                    item.addChild(nft_item)
                    all_items.append(nft_item)

                for nft_in in cat_nfts_in:
                    add_nft(nft_in, False)
                for nft_out in cat_nfts_out:
                    add_nft(nft_out, True)

                if has_minting_ctr:
                    if has_mutable_ctr:
                        item.setToolTip(self.Col.description,
                                        _("Transaction involves {ct1} Minting and {ct2} Mutable NFTs")
                                        .format(ct1=has_minting_ctr, ct2=has_mutable_ctr))
                        item.setIcon(self.Col.description, self.mintingMutableIcon)
                    else:
                        item.setToolTip(self.Col.description,
                                        ngettext("Transaction involves {ct} Minting NFT",
                                                 "Transaction involves {ct} Minting NFTs", has_minting_ctr)
                                        .format(ct=has_minting_ctr))
                        item.setIcon(self.Col.description, self.batonIcon)
                elif has_mutable_ctr:
                    item.setToolTip(self.Col.description,
                                    ngettext("Transaction involves {ct} Mutable NFT",
                                             "Transaction involves {ct} Mutable NFTs", has_mutable_ctr)
                                    .format(ct=has_mutable_ctr))
                    item.setIcon(self.Col.description, self.mutableIcon)

                self.addChild(item)
                all_items.append(item)

        # Restore selections of sub-items, and expanded top-level items
        for item in all_items:
            k = item_key(item)
            if k in selected_keys:
                item.setSelected(True)
            if k in expanded_keys:
                item.setExpanded(True)

        if was_empty:
            # Auto-expand if we have only 1 top-level item with children and this was the first run through
            if self.invisibleRootItem().childCount() == 1:
                self.invisibleRootItem().child(0).setExpanded(True)

    def on_permit_edit(self, item: SortableTreeWidgetItem, column):
        return bool(item.data(0, self.DataRoles.editable_label))

    def on_doubleclick(self, item, column):
        if self.permit_edit(item, column):
            super(TokenHistoryList, self).on_doubleclick(item, column)
        else:
            tx_id = item.data(0, self.DataRoles.tx_hash)
            tx = self.wallet.transactions.get(tx_id)
            if tx:
                self.parent.show_transaction(tx, self.wallet.get_label(tx_id))

    def create_menu(self, position):
        menu = QMenu()

        selected = self.selectedItems()
        num_selected = len(selected)

        def do_copy(txt):
            txt = txt.strip()
            self.parent.copy_to_clipboard(txt)

        col = self.currentColumn()
        column_title = self.headerItem().text(col)

        if num_selected > 0:
            if num_selected == 1:
                item = self.itemAt(position)
                if item:
                    copy_text = item.text(col).strip()
                    nft_row = item.data(0, self.DataRoles.nft_row)
                    if nft_row:
                        description = item.text(self.Col.description).strip()
                        commitment = item.data(0, self.DataRoles.commitment)
                        outpoint = item.data(0, self.DataRoles.outpoint)
                        if description:
                            menu.addAction(_("Copy {}").format(_("NFT Description")), lambda: do_copy(description[2:]))
                        if commitment:
                            menu.addAction(_("Copy {}").format(_("NFT Commitment")), lambda: do_copy(commitment))
                        menu.addAction(_("Copy Outpoint").format(_("Outpoint")), lambda: do_copy(outpoint))
                    elif copy_text:
                        menu.addAction(_("Copy {}").format(column_title), lambda: do_copy(copy_text))

                    tx_hash = item.data(0, self.DataRoles.tx_hash)
                    tx = self.wallet.transactions.get(tx_hash, None)
                    if tx:
                        menu.addAction(_("Details"), lambda: self.parent.show_transaction(tx))

        menu.addSeparator()
        menu.addAction(QIcon(":icons/tab_token.svg"), _("Create Token..."), self.parent.show_create_new_token_dialog)
        menu.exec_(self.viewport().mapToGlobal(position))

    def update_labels(self):
        if self.should_defer_update_incr():
            return
        root = self.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            if not item.data(0, self.DataRoles.editable_label):
                # This item declares its "Description" is not a label, skip
                continue
            txid = item.data(0, self.DataRoles.tx_hash)
            h_label = self.wallet.get_label(txid)
            item.setText(self.Col.description, h_label)
