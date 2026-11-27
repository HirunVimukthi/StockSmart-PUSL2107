from typing import Any


def parse_shelf_location(shelf_location: str) -> tuple[str, int, int]:
    """Parse 'A-01-02' into (aisle_letter, bay_number, shelf_level)."""
    parts = shelf_location.strip().upper().split("-")
    aisle = parts[0] if len(parts) > 0 and parts[0] else "Z"
    try:
        bay = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        bay = 0
    try:
        shelf = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        shelf = 0
    return aisle, bay, shelf


def _aisle_index(aisle: str) -> int:
    """Convert aisle label ('A' -> 0, 'B' -> 1, ...) to zero-based index."""
    if len(aisle) == 1 and "A" <= aisle <= "Z":
        return ord(aisle) - ord("A")
    return 99


def calculate_s_shape_route(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Order warehouse pick items using an S-shape (serpentine) traversal strategy:
    - Aisles are visited in alphabetical order (A -> B -> C ...).
    - Even-index aisles (A, C, E...) traverse bays ascending (1 -> N).
    - Odd-index aisles (B, D, F...) traverse bays descending (N -> 1) to eliminate backtracking.
    """
    if not items:
        return {
            "strategy": "S-Shape Serpentine Optimization",
            "total_stops": 0,
            "estimated_distance_meters": 0.0,
            "route": [],
        }

    def sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
        aisle, bay, shelf = parse_shelf_location(item["shelf_location"])
        idx = _aisle_index(aisle)
        # Serpentine reversal on every second aisle (B, D, F...)
        directional_bay = bay if idx % 2 == 0 else -bay
        directional_shelf = shelf if idx % 2 == 0 else -shelf
        return (idx, directional_bay, directional_shelf, item["sku"])

    optimized = sorted(items, key=sort_key)

    total_distance = 0.0
    prev_aisle_idx = 0
    prev_bay = 0
    formatted_route = []

    for step, item in enumerate(optimized, start=1):
        aisle, bay, shelf = parse_shelf_location(item["shelf_location"])
        aisle_idx = _aisle_index(aisle)

        # Estimate walking distance: 4m between aisles + 2.5m per bay traveled
        aisle_travel = abs(aisle_idx - prev_aisle_idx) * 4.0
        bay_travel = abs(bay - prev_bay) * 2.5
        step_distance = round(aisle_travel + bay_travel + 1.5, 1)
        total_distance += step_distance

        prev_aisle_idx, prev_bay = aisle_idx, bay

        formatted_route.append(
            {
                "step": step,
                "sku": item["sku"],
                "name": item["name"],
                "quantity": item["quantity"],
                "shelf_location": item["shelf_location"],
                "aisle": aisle,
                "bay": bay,
                "shelf": shelf,
                "step_distance_meters": step_distance,
            }
        )

    return {
        "strategy": "S-Shape Serpentine Optimization",
        "total_stops": len(formatted_route),
        "estimated_distance_meters": round(total_distance, 1),
        "route": formatted_route,
    }