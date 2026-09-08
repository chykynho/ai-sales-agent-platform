KNOWN_TOOL_NAMES = (
    "check_price",
    "get_customer_by_email",
    "check_availability",
    "search_knowledge",
    "create_lead",
)
DEFAULT_ENABLED_TOOLS = list(KNOWN_TOOL_NAMES)
DEFAULT_BUSINESS_HOURS = {
    "weekdays": [0, 1, 2, 3, 4],
    "start": "09:00",
    "end": "17:00",
}
