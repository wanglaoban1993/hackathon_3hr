"""Mock idealo-style offers for the two required demo cases.
The idealo teammate replaces these with real MCP data using the same fields:
merchant, price, in_stock, delivery, merchant_rating
"""

PRODUCT = "Sony WH-1000XM5"
BUDGET = 300

ROUTINE_OFFERS = [
    {"merchant": "MediaMarkt", "price": 279.00, "in_stock": True, "delivery": "1-2 days", "merchant_rating": 4.6},
    {"merchant": "Amazon", "price": 281.99, "in_stock": True, "delivery": "1 day", "merchant_rating": 4.7},
    {"merchant": "Otto", "price": 285.00, "in_stock": True, "delivery": "2-3 days", "merchant_rating": 4.4},
]

CONFLICTING_OFFERS = ROUTINE_OFFERS + [
    {"merchant": "cheap-deals24.biz", "price": 149.00, "in_stock": True, "delivery": None, "merchant_rating": None},
]

CASES = {
    "routine": (PRODUCT, BUDGET, ROUTINE_OFFERS),
    "conflicting": (PRODUCT, BUDGET, CONFLICTING_OFFERS),
}
