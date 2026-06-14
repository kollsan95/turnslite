# ============================================================================
# File: main.py
# Role: Central system coordinator, state machine manager, and event loop.
# Description: Orchestrates peripherals, network driver, and barcode scanner.
#              Manages transitions between WORK, WAIT_PASS, and ADMIN states
#              with hard MCU reboots on successful configuration updates.
# ============================================================================

import board
import busio
import microcontroller
import sys
import supervisor
import time
import usb_cdc

from config_manager import ConfigManager
from peripherals import PeripheralsController
from scanner import BarcodeScanner
from ch9120 import CH9120Driver
from http_client import NetworkHttpClient
from passage_sensor import PassageSensor


class AppCore:
    """Main state machine and hardware coordinator."""

    def __init__(self):
        """Initialize all subsystems, network, and fallback to WORK state."""
        print("🚀 [SYSTEM]: Initialization started...")
        self.cfg = ConfigManager()

        # Start with all indicators off
        self.peripherals = PeripheralsController()
        self.peripherals.set_led_color(0, 0, 0)

        # UART pins for CH9120 (Ethernet)
        self.uart_tx_pin = getattr(board, self.cfg.get("uart_tx", "GP20"))
        self.uart_rx_pin = getattr(board, self.cfg.get("uart_rx", "GP21"))
        self.working_baudrate = int(self.cfg.get("baudrate", 115200))

        self.uart = busio.UART(
            self.uart_tx_pin,
            self.uart_rx_pin,
            baudrate=self.working_baudrate,
            timeout=1.0
        )

        # Barcode scanner connected via USB host (GP0/GP1)
        self.scanner = BarcodeScanner()

        # Passage sensor (e.g., IR barrier)
        self.passage_sensor = PassageSensor()

        # CH9120 Ethernet driver and network config
        self.ch9120_driver = CH9120Driver(
            self.uart,
            getattr(board, self.cfg.get("pin_cfg", "GP18")),
            getattr(board, self.cfg.get("pin_rst", "GP19")),
            self.working_baudrate
        )
        self.ch9120_driver.apply_network_settings(self.cfg)

        # Optional DHCP waiting period
        if int(self.cfg.get("dhcp", 1)) == 1:
            self.peripherals.set_led_processing()  # Yellow LED
            print("⏳ [NETWORK]: DHCP Mode. Awaiting IP allocation...")
            time.sleep(5.0)

        self.http_client = NetworkHttpClient(self.ch9120_driver, self.cfg)

        # Final ready state: solid red LED
        self.peripherals.trigger_access_denied()
        print("🟢 [SYSTEM]: Turnstile Engine Ready.")

        # State variables
        self.system_state = "WORK"          # WORK / WAIT_PASS / ADMIN
        self.password_timer = 5.0           # Monotonic timestamp for 5s timeout

    # -------------------------------------------------------------------------
    # State handlers
    # -------------------------------------------------------------------------
    def _process_work_mode(self, scanned_code: str, admin_login: str) -> None:
        """
        Normal turnstile operation: check ticket code via HTTP.
        If the scanned code equals the admin login code, switch to WAIT_PASS.
        """
        if scanned_code == admin_login:
            self.system_state = "WAIT_PASS"
            self.peripherals.set_led_admin()        # Purple / admin LED
            
        else:
            self.peripherals.set_led_processing()   # Yellow LED
            print(f"🎫 [TICKET]: '{scanned_code}'")

            is_allowed = self.http_client.send_barcode(scanned_code)

            # --- Output the server verdict ---
            print(f"allowed: {str(is_allowed).lower()}")

            if is_allowed:
                self.peripherals.set_led_color(0, 60, 0)   # Solid green
                self.peripherals.trigger_relay_1(duration=2.0)
                self.passage_sensor.wait_for_passage(timeout=2.0)
            else:
                self.peripherals.trigger_access_denied()   # Blinks red 1s

            # Return to solid red (operational state)
            self.peripherals.set_led_color(40, 0, 0)

    def _process_wait_pass_mode(self, scanned_code: str, admin_password: str) -> None:
        """
        Admin password challenge.
        - Correct: unlock ADMIN state, flash both relays.
        - Wrong:   return to WORK, flush buffer, flash relays twice.
        """
        if scanned_code == admin_password:
            print("🔓 [ADMIN]: Admin panel UNLOCKED.")
            self.system_state = "ADMIN"
            self.peripherals.set_led_admin()
            self.peripherals.trigger_admin_approved()
        else:
            print("❌ [SECURITY]: Invalid admin password!")
            self.system_state = "WORK"
            self.peripherals.set_led_color(40, 0, 0)           # Solid red
            # Flush any remaining input (partial lines, extra CR)
            self.peripherals.trigger_admin_declined()

    def _process_admin_mode(self, scanned_code: str, admin_password: str) -> None:
        """
        Admin mode commands:
        - If the code equals the admin password: reboot the MCU.
        - Otherwise treat the code as a configuration payload (JSON).
          If valid, save and reboot; if invalid, flash error and flush buffer.
        """
        if scanned_code == admin_password:
            print("🔄 [ADMIN]: Reboot command received. Rebooting MCU...")
            self.peripherals.trigger_admin_approved()
            microcontroller.reset()
        else:
            print("📝 [ADMIN]: Processing configuration payload...")
            if self.cfg.validate_and_merge(scanned_code):
                print("💾 [ADMIN]: New settings saved. Rebooting...")
                self.peripherals.trigger_admin_approved()
                microcontroller.reset()
            else:
                print("❌ [ADMIN]: Configuration validation failed.")
                # Flush potentially malformed data that might be stuck
                self.peripherals.trigger_admin_declined()

    # -------------------------------------------------------------------------
    # Main event loop
    # -------------------------------------------------------------------------
    def run(self) -> None:
        """
        Main state machine loop.
        - WORK:       fully blocking wait_for_scan() – ideal for barcode input.
        - WAIT_PASS / ADMIN: non‑blocking polling using try_read_scan()
                      to respect the 5‑second password timeout.
        """
        admin_login = str(self.cfg.get("admin_code", "admin")).strip()
        admin_password = str(self.cfg.get("admin_pass", "12345")).strip()

        while True:
            if self.system_state == "WAIT_PASS":
                password = self.scanner.try_read_scan(self.password_timer)
                self._process_wait_pass_mode(password, admin_password)
                
            if self.system_state == "WORK":
                # Always start by discarding any residual noise (e.g., spurious CR)
                self.scanner.flush_buffer()
                # ----- BLOCKING read (perfect for WORK mode) -----
                scanned_code = self.scanner.wait_for_scan()
                if scanned_code:
                    self._process_work_mode(scanned_code, admin_login)
                    
            elif self.system_state == "ADMIN":
                scanned_code = self.scanner.try_read_scan(30.0)
                self._process_admin_mode(scanned_code, admin_password)
                
if __name__ == "__main__":
    app = AppCore()
    app.run()
    