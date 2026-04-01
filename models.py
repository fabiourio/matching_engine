from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class OrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"
    PEGGED = "pegged"


class PegSide(Enum):
    BID = "bid"
    OFFER = "offer"


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class EventType(Enum):
    ORDER_CREATED = "order_created"
    TRADE = "trade"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_AMENDED = "order_amended"
    ORDER_REJECTED = "order_rejected"
    ORDER_PEGGED = "order_pegged"
    ERROR = "error"


@dataclass
class Order:
    order_id: str
    order_type: OrderType
    side: Side
    qty: int
    seq: int
    price: Optional[Decimal] = None
    active: bool = True
    peg_side: Optional[PegSide] = None
    # order points to its node for O(1) access inside doubly linked list
    _node: Optional[Any] = field(default = None, repr = False, compare = False)

    def __post_init__(self):
        if self.qty <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("limit orders must have a price")
        if self.order_type == OrderType.MARKET and self.price is not None:
            raise ValueError("market orders must not have a price")
        if self.order_type == OrderType.PEGGED and self.peg_side is None:
            raise ValueError("pegged orders must have a peg_side")


@dataclass
class EngineEvent:
    event_type: EventType
    message: Optional[str] = None
    order_id: Optional[str] = None
    side: Optional[Side] = None
    price: Optional[Decimal] = None
    qty: Optional[int] = None
    buyer_id: Optional[str] = None
    seller_id: Optional[str] = None

    def render(self, detailed: bool = True) -> str:
        match self.event_type:
            case EventType.ORDER_CREATED:
                assert self.order_id is not None
                assert self.side is not None
                assert self.price is not None
                assert self.qty is not None
                return f"Order created: {self.side.value} {self.qty} @ {self.price} {self.order_id}"
            case EventType.TRADE:
                assert self.price is not None
                assert self.qty is not None
                if detailed and self.buyer_id and self.seller_id:
                    return f"Trade: {self.buyer_id} x {self.seller_id}, price: {self.price}, qty: {self.qty}"
                return f"Trade, price: {self.price}, qty: {self.qty}"
            case EventType.ORDER_CANCELLED:
                return "Order cancelled"
            case EventType.ORDER_AMENDED:
                return "Order amended"
            case EventType.ORDER_REJECTED:
                assert self.qty is not None
                return f"Order rejected: {self.qty} unfilled"
            case EventType.ORDER_PEGGED:
                assert self.order_id is not None
                assert self.side is not None
                assert self.qty is not None
                if detailed:
                    return f"Order pegged: {self.side.value} {self.qty} {self.order_id}"
                return f"Order pegged: {self.side.value} {self.qty}"
            case _:
                return self.message or "Error"


def aggregate_trades(events: list[EngineEvent]) -> list[EngineEvent]:
    out: list[EngineEvent] = []
    for ev in events:
        if (ev.event_type == EventType.TRADE
                and out and out[-1].event_type == EventType.TRADE
                and out[-1].price == ev.price):
            out[-1].qty += ev.qty
        else:
            out.append(ev)
    return out