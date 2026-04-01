from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Union

from models import PegSide, Side


@dataclass
class LimitCommand:
    side: Side
    price: Decimal
    qty: int

@dataclass
class MarketCommand:
    side: Side
    qty: int

@dataclass
class PeggedCommand:
    side: Side
    peg_side: PegSide
    qty: int
    
@dataclass
class CancelCommand:
    order_id: str

@dataclass
class AmendCommand:
    order_id: str
    new_price: Optional[Decimal] = None
    new_qty: Optional[int] = None

@dataclass
class PrintBookCommand:
    pass

@dataclass
class QuitCommand:
    pass


ParsedCommand = Union[LimitCommand, MarketCommand, CancelCommand,
                       AmendCommand, PeggedCommand, PrintBookCommand, QuitCommand]


def parse_command(line: str) -> ParsedCommand:
    tokens = line.strip().split()
    if not tokens:
        raise ValueError("Empty command")

    head = tokens[0].lower()

    if head in {"quit", "exit"}:
        return QuitCommand()
    if head == "print":
        if len(tokens) != 2 or tokens[1].lower() != "book":
            raise ValueError("Usage: print book")
        return PrintBookCommand()
    if head == "limit":
        return _parse_limit(tokens)
    if head == "market":
        return _parse_market(tokens)
    if head == "cancel":
        return _parse_cancel(tokens)
    if head == "amend":
        return _parse_amend(tokens)
    if head == "peg":
        return _parse_pegged(tokens)

    raise ValueError(f"Unknown command: {tokens[0]}")


def _parse_limit(tokens: list[str]) -> LimitCommand:
    if len(tokens) != 4:
        raise ValueError("Usage: limit <buy|sell> <price> <qty>")
    return LimitCommand(side = _side(tokens[1]), price = _price(tokens[2]), qty = _qty(tokens[3]))


def _parse_market(tokens: list[str]) -> MarketCommand:
    if len(tokens) != 3:
        raise ValueError("Usage: market <buy|sell> <qty>")
    return MarketCommand(side = _side(tokens[1]), qty = _qty(tokens[2]))


def _parse_cancel(tokens: list[str]) -> CancelCommand:
    if len(tokens) == 2:
        return CancelCommand(order_id = tokens[1])
    if len(tokens) == 3 and tokens[1].lower() == "order":
        return CancelCommand(order_id = tokens[2])
    raise ValueError("Usage: cancel <order_id>  or  cancel order <order_id>")


def _parse_pegged(tokens: list[str]) -> PeggedCommand:
    if len(tokens) != 4:
        raise ValueError("Usage: peg <buy|sell> <bid|offer> <qty>")
    return PeggedCommand(side = _side(tokens[1]), peg_side = _peg_side(tokens[2]), qty = _qty(tokens[3]))


def _parse_amend(tokens: list[str]) -> AmendCommand:
    if len(tokens) < 4:
        raise ValueError("Usage: amend <order_id> [price <p>] [qty <q>]")

    order_id = tokens[1]
    new_price, new_qty, i = None, None, 2

    while i < len(tokens):
        field = tokens[i].lower()
        if i + 1 >= len(tokens):
            raise ValueError(f"Missing value after '{field}'")
        if field == "price":
            new_price = _price(tokens[i + 1])
        elif field == "qty":
            new_qty = _qty(tokens[i + 1])
        else:
            raise ValueError(f"Unknown amend field: {tokens[i]}")
        i += 2

    if new_price is None and new_qty is None:
        raise ValueError("Usage: amend <order_id> [price <p>] [qty <q>]")
    return AmendCommand(order_id = order_id, new_price = new_price, new_qty = new_qty)

def _peg_side(token: str) -> PegSide:
    t = token.lower()
    if t == "bid":  return PegSide.BID
    if t == "offer":  return PegSide.OFFER
    raise ValueError("Peg side must be 'bid' or 'offer'")

def _side(token: str) -> Side:
    t = token.lower()
    if t == "buy":  return Side.BUY
    if t == "sell": return Side.SELL
    raise ValueError("Side must be 'buy' or 'sell'")

def _price(token: str) -> Decimal:
    try:
        p = Decimal(token)
    except InvalidOperation as e:
        raise ValueError(f"Invalid price: {token}") from e
    if p <= 0:
        raise ValueError("Price must be positive")
    # assuming we won't work with more than 2
    if p.as_tuple().exponent < -2:
        raise ValueError("Price cannot have more than 2 decimal places")
    return p

def _qty(token: str) -> int:
    try:
        q = int(token)
    except ValueError as e:
        raise ValueError(f"Invalid qty: {token}") from e
    if q <= 0:
        raise ValueError("Qty must be positive")
    return q