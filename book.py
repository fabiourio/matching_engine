from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sortedcontainers import SortedList

from models import Order, OrderType, PegSide, Side


class Node:
    __slots__ = ("order", "prev", "next")

    def __init__(self, order: Order | None = None):
        self.order = order
        self.prev: Node | None = None
        self.next: Node | None = None


class DoublyLinkedList:

    # standard DLL methods
    def __init__(self):
        self._head = Node()
        self._tail = Node()
        self._head.next = self._tail
        self._tail.prev = self._head
        self._size = 0

    def append(self, order: Order) -> Node:
        node = Node(order)
        prev = self._tail.prev
        prev.next = node
        node.prev = prev
        node.next = self._tail
        self._tail.prev = node
        self._size += 1
        order._node = node
        return node

    def remove(self, node: Node):
        node.prev.next = node.next
        node.next.prev = node.prev
        node.prev = None
        node.next = None
        self._size -= 1

    def peek(self) -> Order | None:
        if self._size == 0:
            return None
        return self._head.next.order

    def __bool__(self):
        return self._size > 0

    def __len__(self):
        return self._size

    def __iter__(self):
        curr = self._head.next
        while curr is not self._tail:
            yield curr.order
            curr = curr.next


class BookSide:

    def __init__(self, side: Side):
        self.side = side
        self._prices: SortedList[Decimal] = SortedList()
        self._levels: dict[Decimal, DoublyLinkedList] = {}
        self.peg_bid = DoublyLinkedList()
        self.peg_offer = DoublyLinkedList()

    @property
    def best_price(self) -> Optional[Decimal]:
        if not self._prices:
            return None
        if self.side == Side.BUY:
            return self._prices[-1]
        else:
            return self._prices[0]

    def add_limit(self, order: Order):
        price = order.price
        if price not in self._levels:
            self._levels[price] = DoublyLinkedList()
            self._prices.add(price)
        self._levels[price].append(order)

    def add_pegged(self, order: Order):
        if order.peg_side == PegSide.BID:
            self.peg_bid.append(order)
        else:
            self.peg_offer.append(order)

    def remove_order(self, order: Order):
        node = order._node
        if node is None:
            return

        if order.order_type == OrderType.PEGGED:
            if order.peg_side == PegSide.BID:
                dll = self.peg_bid
            else:
                dll = self.peg_offer
            dll.remove(node)
        elif order.order_type == OrderType.LIMIT:
            price = order.price
            level = self._levels[price]
            level.remove(node)
            if not level:
                del self._levels[price]
                self._prices.remove(price)

        order._node = None
        order.active = False


class OrderBook:

    def __init__(self):
        self.buy = BookSide(Side.BUY)
        self.sell = BookSide(Side.SELL)

    def side_of(self, side: Side) -> BookSide:
        if side == Side.BUY:
            return self.buy
        else:
            return self.sell

    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.buy.best_price

    @property
    def best_offer(self) -> Optional[Decimal]:
        return self.sell.best_price

    # all orders sorted for display
    def _collect_side(self, book_side: BookSide) -> list[tuple[Optional[Decimal], int, Order, str]]:
        entries: list[tuple[Optional[Decimal], int, Order, str]] = []
        for price in book_side._prices:
            for order in book_side._levels[price]:
                entries.append((price, order.seq, order, "limit"))

        bid, offer = self.best_bid, self.best_offer
        for order in book_side.peg_bid:
            entries.append((bid, order.seq, order, "peg bid"))
        for order in book_side.peg_offer:
            entries.append((offer, order.seq, order, "peg offer"))

        priced = [e for e in entries if e[0] is not None]
        unpriced = [e for e in entries if e[0] is None]
        priced.sort(key = lambda e: (-e[0], e[1]))
        unpriced.sort(key = lambda e: e[1])
        return priced + unpriced

    def format_book(self, detailed: bool = True) -> str:
        lines: list[str] = []
        lines.append("=== ORDER BOOK ===")
        lines.append(f"  Best bid: {self.best_bid}  Best offer: {self.best_offer}")

        for label, book_side in [("SELL", self.sell), ("BUY", self.buy)]:
            lines.append(f"--- {label} ---")
            for price, _, order, tag in self._collect_side(book_side):
                price_str = str(price) if price is not None else "--"
                if detailed:
                    tag_str = f" [{tag}]" if tag != "limit" else ""
                    lines.append(f"  {order.order_id}: {order.qty} @ {price_str}{tag_str}")
                else:
                    lines.append(f"  {order.qty} @ {price_str}")

        return "\n".join(lines)