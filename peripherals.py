# ============================================================================
# File: peripherals.py
# Role: Hardware actuator manager and multi-color indicator controller.
# Description: Directly activates dual output driving relay lines and passes
#              raw bitstreams into the onboard WS2812 GRB light emitting element.
# ============================================================================

import board
import digitalio
import neopixel_write
import time

class PeripheralsController:
    def __init__(self, pin_r1=board.GP26, pin_r2=board.GP27, pin_led=board.GP25):
        """
        Provisions physical output pin modes for physical entry/exit relays
        and locks the status indicator into default restricted dark profiles.
        """
        self.relay_1 = digitalio.DigitalInOut(pin_r1)
        self.relay_1.direction = digitalio.Direction.OUTPUT
        self.relay_1.value = False

        self.relay_2 = digitalio.DigitalInOut(pin_r2)
        self.relay_2.direction = digitalio.Direction.OUTPUT
        self.relay_2.value = False

        self.led_pin = digitalio.DigitalInOut(pin_led)
        self.led_pin.direction = digitalio.Direction.OUTPUT
        
        self.set_led_closed()

    def set_led_color(self, g: int, r: int, b: int):
        """
        Low-level driver bridge. Packs bit sequences using the standard GRB format
        and clocks it out to the NeoPixel without leveraging heavy external libraries.
        """
        color_bytes = bytearray([g, r, b])
        neopixel_write.neopixel_write(self.led_pin, color_bytes)

    def set_led_closed(self):
        """
        Switches the system indicator into a fully turned off profile during standby.
        """
        self.set_led_color(40, 0, 0)

    def set_led_processing(self):
        """
        Switches the system indicator into an energetic Yellow profile, indicating
        active authorization transactions over networking interfaces.
        """
        self.set_led_color(25, 25, 0)

    def set_led_success(self):
        """
        Switches the system indicator into a solid Green profile, confirming that
        mechanisms are open for human entry.
        """
        self.set_led_color(0, 40, 0)

    def set_led_admin(self):
        """
        Switches the system indicator into a solid Orange profile, signaling that
        engineering and system adjustments interfaces are currently active.
        """
        self.set_led_color(40, 13, 0)

    def trigger_access_denied(self):
        """
        Executes a non-blocking hardware alert state: blinks the red LED 
        exactly 2 times within a strict 1-second bounded window. 
        Relays remain untouched.
        """
        for _ in range(2):
            self.set_led_color(0, 0, 0)
            time.sleep(0.25)
            self.set_led_color(40, 0, 0)
            time.sleep(0.25)
            
    def trigger_both_relays(self, duration: float):
        """
        Engages entry and exit actuators simultaneously for a bounded time frame.
        Commonly deployed to feed acoustic clicks to administrators.
        """
        self.relay_1.value = True
        self.relay_2.value = True
        time.sleep(duration)
        self.relay_1.value = False
        self.relay_2.value = False

    def trigger_relay_1(self, duration=2.0):
        """
        Energizes the primary entry turnstile lock driving transistor line,
        holds state, then disengages lines.
        """
        self.relay_1.value = True
        time.sleep(duration)
        self.relay_1.value = False

    def trigger_relay_2(self, duration=2.0):
        """
        Energizes the secondary exit turnstile lock driving transistor line,
        holds state, then disengages lines.
        """
        self.relay_2.value = True
        time.sleep(duration)
        self.relay_2.value = False
        
    def trigger_admin_declined(self):
        """
        Double short activation of both relays (0.5s on, 0.5s off, 0.5s on).
        Used to indicate successful admin authentication or configuration save.
        """
        self.trigger_both_relays(0.5)
        time.sleep(0.5)
        self.trigger_both_relays(0.5)

    def trigger_admin_approved(self):
        """
        Single long activation of both relays (1.0 second).
        Used to indicate access denied or configuration failure.
        """
        self.trigger_both_relays(1.0)