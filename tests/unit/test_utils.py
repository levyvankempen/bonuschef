from datetime import datetime
from bonuschef.utils.utils import greeting_based_on_time

def test_greeting_morning():
    morning_time = datetime(2024, 1, 1, 8, 0, 0)
    assert greeting_based_on_time(morning_time) == "Good morning"

