def ensure_positive_int(value: int, field: str) -> int:
    if value is None or int(value) < 0:
        raise ValueError(f"{field} must be >= 0")
    return int(value)


