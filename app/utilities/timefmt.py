from datetime import timedelta


def format_duration(delta: timedelta) -> str:
    """Short human duration, rounded down to minutes: '3h 12m', '7 min'."""
    minutes = max(int(delta.total_seconds() // 60), 1)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes} min"
