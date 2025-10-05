from datetime import datetime

def greeting_based_on_time(current_time: datetime | None = None) -> str:
    """Return a greeting depending on the time of day."""
    if current_time is None:
        current_time = datetime.now()

    hour = current_time.hour

    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 18:
        return "Good afternoon"
    elif 18 <= hour < 22:
        return "Good evening"
    else:
        return "Good night"
