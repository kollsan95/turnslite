# ============================================================================
# File: passage_sensor.py
# Class: PassageSensor
# Role: Turnstile hardware tracking module and physical verification sensor.
# Status: Non-blocking mock object ready for future optocoupler/reed switch wiring.
# Logic: Implements a precise time.sleep() software loop that holds turnstile state 
#        and confirms individual human movement through the gate array.
# ============================================================================

import time

class PassageSensor:
    """Класс-заглушка для датчика контроля прохода через турникет."""
    
    def __init__(self):
        pass

    def wait_for_passage(self, timeout=2.0) -> bool:
        """
        Имитирует ожидание прохода человека. 
        Удерживает паузу 2 секунды и гарантированно возвращает True.
        """
        time.sleep(timeout)
        return True