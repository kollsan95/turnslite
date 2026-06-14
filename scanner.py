# ============================================================================
# File: scanner.py for RD2040-ETH Waveshare
# Role: Hardware barcode scanner driver and stream interpreter.
# Description: Streamlined line-reading adapter leveraging sys.stdin.readline.
#              Uses USB host on GP0/GP1 to receive HID keyboard input from a
#              barcode scanner (emulating a keyboard). Provides blocking read
#              and buffer flushing utilities.
# ============================================================================

import board          # Pin definitions for the board (GP0, GP1, etc.)
import sys            # Standard input stream (sys.stdin) for reading scanned data
import usb_host       # CircuitPython USB Host API (to initialize host on specific pins)
import supervisor     # Provides runtime.serial_bytes_available to check pending data
import time

class BarcodeScanner:
    """
    Driver for a USB barcode scanner that behaves like a keyboard.
    The scanner is connected to the USB host pins (D+ and D-), typically GP0 and GP1.
    Data is received as lines of text terminated by '\\r' (carriage return).
    """

    def __init__(self, pin_dp=None, pin_dm=None):
        """
        Initializes the USB host interface on the designated D+ and D- lines.

        :param pin_dp: Pin for USB D+ (default: board.GP0)
        :param pin_dm: Pin for USB D- (default: board.GP1)
        """
        # Use default pins if not provided
        if pin_dp is None:
            pin_dp = board.GP0
        if pin_dm is None:
            pin_dm = board.GP1

        # Store the port object for potential external access
        self.port = None

        # Attempt to create the USB host port.
        # This configures the RP2040's PIO to act as a USB host on the specified pins.
        try:
            self.port = usb_host.Port(pin_dp, pin_dm)
            print(f"[SCANNER] USB Host port initialized on DP={pin_dp}, DM={pin_dm}")
        except RuntimeError as e:
            # Common error: port already created or pins already in use
            print(f"[SCANNER WARNING] Could not create USB host port: {e}")
        except Exception as e:
            # Catch any other unexpected exceptions during port creation
            print(f"[SCANNER ERROR] Unexpected exception: {e}")

    def get_port(self):
        """
        Returns the underlying usb_host.Port object (may be None if initialization failed).
        Useful for low-level control or debugging.
        """
        return self.port

    def flush_buffer(self):
        """
        Reads and discards all pending data from the input buffer.
        This is important after timeouts, errors, or state transitions to remove
        stale or partial lines that might have accumulated in the FIFO.
        """
        # supervisor.runtime.serial_bytes_available returns the number of bytes
        # waiting in the USB CDC input buffer (which is the same as sys.stdin).
        while supervisor.runtime.serial_bytes_available > 0:
            # Read and throw away one whole line (including the terminating '\\r')
            _ = sys.stdin.readline()
            time.sleep(0.02)
            

    def wait_for_scan(self) -> str:
        """
        Blocks until a full line (terminated by '\\r') is received from the scanner.
        Returns the scanned code as a stripped string (without leading/trailing whitespace).
        If an error occurs, returns an empty string and prints an error message.
        """
        try:
            # sys.stdin.readline() is blocking – it will wait indefinitely until
            # a carriage return ('\\r') is received. This is perfect for barcode
            # scanners that send data as a line of text ending with CR.
            line = sys.stdin.readline()
            # Strip whitespace (including newline/carriage return) and return
            return line.strip()
        except OSError as e:
            # Possible OS-level I/O error (e.g., USB disconnection, buffer corruption)
            print(f"[SCANNER ERROR] Read error: {e}")
            return ""
        except Exception as e:
            # Any other unexpected exception during reading
            print(f"[SCANNER ERROR] Unexpected read error: {e}")
            return ""
        
    def try_read_scan(self, timeout: float = 0.5) -> str | None:
        """
        Read one line (terminated by '\n') with a timeout.
        Returns stripped line if a complete line is received within timeout,
        otherwise returns None.
        """
        start = time.monotonic()
        chars = []
        while (time.monotonic() - start) < timeout:
            if supervisor.runtime.serial_bytes_available > 0:
                ch = sys.stdin.read(1)
                if ch == '\n':
                    return ''.join(chars).strip()
                else:
                    chars.append(ch)
            # optional small sleep to reduce CPU usage
            time.sleep(0.02)
        return None