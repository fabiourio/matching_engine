from decimal import Decimal
from typing import Optional

from models import EngineEvent, EventType, Order, OrderType, PegSide, Side
from book import OrderBook, BookSide


class MatchingEngine:

    def __init__(self):
        self.book = OrderBook()
        self._orders: dict[str, Order] = {}
        self._seq = 0
        self._order_counter = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _next_id(self) -> str:
        self._order_counter += 1
        return f"id_{self._order_counter}"

    def submit_limit(self, side: Side, price: Decimal, qty: int) -> list[EngineEvent]:
        order = Order(
            order_id = self._next_id(), order_type = OrderType.LIMIT,
            side = side, qty = qty, seq = self._next_seq(), price = price,
        )
        
        # match when it arrives, then submit the remaining
        events = self._match(order)
        if order.qty > 0:
            self._orders[order.order_id] = order
            self.book.side_of(side).add_limit(order)
            events.append(EngineEvent(
                event_type = EventType.ORDER_CREATED,
                order_id = order.order_id, side = side, price = price, qty = order.qty,
            ))
        return events

    def submit_market(self, side: Side, qty: int) -> list[EngineEvent]:
        order = Order(
            order_id = self._next_id(), order_type = OrderType.MARKET,
            side = side, qty = qty, seq = self._next_seq(),
        )
        events = self._match(order)
        if order.qty > 0:
            events.append(EngineEvent(event_type = EventType.ORDER_REJECTED, qty = order.qty))
        return events

    def submit_pegged(self, side: Side, peg_side: PegSide, qty: int) -> list[EngineEvent]:
        order = Order(
            order_id = self._next_id(), order_type = OrderType.PEGGED,
            side = side, qty = qty, seq = self._next_seq(), peg_side = peg_side,
        )
        events = self._match(order)
        if order.qty > 0:
            self._orders[order.order_id] = order
            self.book.side_of(side).add_pegged(order)
            events.append(EngineEvent(
                event_type = EventType.ORDER_PEGGED,
                order_id = order.order_id, side = side, qty = order.qty,
            ))
        return events

    def cancel_order(self, order_id: str) -> list[EngineEvent]:
        order = self._orders.get(order_id)
        if order is None or not order.active:
            return [EngineEvent(event_type = EventType.ERROR,
                                message = f"Order {order_id} not found or inactive")]
        self.book.side_of(order.side).remove_order(order)
        del self._orders[order_id]
        return [EngineEvent(event_type = EventType.ORDER_CANCELLED, order_id = order_id)]

    def amend_order(self, order_id: str,
                    new_price: Optional[Decimal] = None,
                    new_qty: Optional[int] = None) -> list[EngineEvent]:
        order = self._orders.get(order_id)
        if order is None or not order.active:
            return [EngineEvent(event_type = EventType.ERROR,
                                message = f"Order {order_id} not found or inactive")]
        if order.order_type == OrderType.MARKET:
            return [EngineEvent(event_type = EventType.ERROR,
                                message = "Market orders cannot be amended")]
        if order.order_type == OrderType.PEGGED and new_price is not None:
            return [EngineEvent(event_type = EventType.ERROR,
                                message = "Cannot set price on a pegged order")]

        # if amended, order loses priority
        self.book.side_of(order.side).remove_order(order)

        if new_price is not None:
            order.price = new_price
        if new_qty is not None:
            order.qty = new_qty
        order.seq = self._next_seq()
        order.active = True

        events = self._match(order)
        if order.qty > 0:
            if order.order_type == OrderType.LIMIT:
                self.book.side_of(order.side).add_limit(order)
            else:
                self.book.side_of(order.side).add_pegged(order)
            events.append(EngineEvent(
                event_type = EventType.ORDER_AMENDED,
                order_id = order_id, side = order.side, price = order.price, qty = order.qty,
            ))
        else:
            del self._orders[order_id]
        return events

    def _effective_price(self, order: Order) -> Optional[Decimal]:
        if order.order_type == OrderType.LIMIT:
            return order.price
        if order.order_type == OrderType.PEGGED:
            if order.peg_side == PegSide.BID:
                return self.book.best_bid
            return self.book.best_offer
        return None

    # returns highest-priority resting order as (effective_price, order)
    def _best_resting(self, book_side: BookSide,
                      incoming: Optional[Order] = None) -> Optional[tuple[Decimal, Order]]:
        best_bid = self.book.best_bid
        best_offer = self.book.best_offer

        # need to consider incoming limit if a pegged order came before
        if incoming is not None and incoming.order_type == OrderType.LIMIT:
            if incoming.side == Side.BUY:
                if best_bid is None or incoming.price > best_bid:
                    best_bid = incoming.price
            else:
                if best_offer is None or incoming.price < best_offer:
                    best_offer = incoming.price

        is_buy = (book_side.side == Side.BUY)

        # get the best from each - limit, peg to bid, peg to offer - and sort
        candidates: list[tuple[Decimal, int, Order]] = []

        # best limit price
        bp = book_side.best_price
        if bp is not None:
            head = book_side._levels[bp].peek()
            if head:
                if is_buy:
                    key = -bp
                else:
                    key = bp
                candidates.append((key, head.seq, head))

        # pegged to the bid
        if best_bid is not None and book_side.peg_bid:
            head = book_side.peg_bid.peek()
            if head:
                if is_buy:
                    key = -best_bid
                else:
                    key = best_bid
                candidates.append((key, head.seq, head))

        # pegged to the offer
        if best_offer is not None and book_side.peg_offer:
            head = book_side.peg_offer.peek()
            if head:
                if is_buy:
                    key = -best_offer
                else:
                    key = best_offer
                candidates.append((key, head.seq, head))

        if not candidates:
            return None
        candidates.sort() # price first, then seq
        winner = candidates[0]
        if is_buy:
            eff_price = -winner[0]
        else:
            eff_price = winner[0]
        return eff_price, winner[2]

    def _match(self, incoming: Order) -> list[EngineEvent]:
        events: list[EngineEvent] = []
        opposite = self.book.side_of(Side.SELL if incoming.side == Side.BUY else Side.BUY)

        while incoming.qty > 0:
            best_opposite_resting = self._best_resting(opposite, incoming)
            if best_opposite_resting is None:
                break
            eff_price, resting = best_opposite_resting

            # price compatibility
            if incoming.order_type == OrderType.LIMIT:
                if incoming.side == Side.BUY and eff_price > incoming.price:
                    break
                if incoming.side == Side.SELL and eff_price < incoming.price:
                    break
            elif incoming.order_type == OrderType.PEGGED:
                inc_price = self._effective_price(incoming)
                if inc_price is None:
                    break
                if incoming.side == Side.BUY and eff_price > inc_price:
                    break
                if incoming.side == Side.SELL and eff_price < inc_price:
                    break

            trade_qty = min(incoming.qty, resting.qty)
            incoming.qty -= trade_qty
            resting.qty -= trade_qty

            # for display
            if incoming.side == Side.BUY:
                buyer_id, seller_id = incoming.order_id, resting.order_id
            else:
                buyer_id, seller_id = resting.order_id, incoming.order_id
            events.append(EngineEvent(
                event_type = EventType.TRADE, price = eff_price, qty = trade_qty,
                buyer_id = buyer_id, seller_id = seller_id,
            ))

            if resting.qty == 0:
                opposite.remove_order(resting)
                self._orders.pop(resting.order_id, None)

        return events
