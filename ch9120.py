# ============================================================================
# File: ch9120.py
# Role: Low-level driver for the WCH CH9120 hardwired TCP/IP transceiver.
# Description: Implements physical configurations using the CFG/RST pin sequence
#              and pushes structural network properties directly into register blocks.
# ============================================================================

import board
import busio
import digitalio
import microcontroller
import time

class CH9120Driver:
    def __init__(self, uart_object, cfg_pin, rst_pin, working_baudrate=115200):
        """
        Binds a pre-initialized system-wide UART line reference and sets up
        executive configuration and hardware reset pins in a high state.
        """
        self.uart = uart_object
        self.cfg_pin = cfg_pin
        self.rst_pin = rst_pin
        self.working_baudrate = working_baudrate
        
        self.cfg = digitalio.DigitalInOut(self.cfg_pin)
        self.cfg.switch_to_output(value=True)
        
        self.rst = digitalio.DigitalInOut(self.rst_pin)
        self.rst.switch_to_output(value=True)

    def _enter_config(self):
        """
        Forces the physical control states layout to capture the command context.
        DOCUMENTATION FIX: Downscales UART speed to 9600 BEFORE shifting control lines.
        CFG line pulled LOW BEFORE RST line transitions high to force hardware config latch.
        """
        self.uart.baudrate = 9600                # Hardware constraint: config loops require 9600 baud
        time.sleep(0.05)
        
        self.cfg.value = False                  # Step 1: Force CFG line to ground (LOW)
        time.sleep(0.05)
        self.rst.value = False                  # Step 2: Force RESET line to ground (LOW)
        time.sleep(0.1)                         # Step 3: Hardware reset pulse duration window
        self.rst.value = True                   # Step 4: Release RESET (transceiver samples LOW on CFG)
        time.sleep(0.5)                         # Step 5: Wait for internal firmware boot sequence
        self.uart.reset_input_buffer()          # Flush transitional electrical switching noise

    def _exit_config_and_save(self):
        """
        Sends the physical factory commit triad sequence to save register fields to internal EEPROM,
        clears configuration lines, and resets the system UART back to operational settings.
        """
        for cmd in (b'\x57\xab\x0D', b'\x57\xab\x0E', b'\x57\xab\x5E'):
            self.uart.write(cmd) 
            time.sleep(0.1)      
            
        self.cfg.value = True    # Release CFG line to HIGH (return to transparent mode)
        time.sleep(3.0)          # CRITICAL FIX: Safe physical hardware timeline for internal reboot execution
        
        self.uart.baudrate = self.working_baudrate
        time.sleep(0.1)

    def _ip_to_bytes(self, ip_str: str) -> bytes:
        """
        Helper utility translating standard string IPv4 addresses (e.g. '192.168.1.1')
        into literal 4-byte structures expected by network chip interfaces.
        """
        return bytes(int(x) for x in ip_str.split('.'))

    def apply_network_settings(self, cfg_manager):
        """
        Monolithic register writing block. Modifies DHCP status, network addresses,
        target host connections, and port configurations in little-endian format.
        """
        dhcp_status = int(cfg_manager.get("dhcp", 1))
        
        # FIXED STORAGE ASSIGNMENT: Writes safely to zero index inside core NVM bytearray
        microcontroller.nvm[0] = 1 if dhcp_status == 1 else 0
        
        self._enter_config()
        
        dhcp_val = b'\x01' if dhcp_status == 1 else b'\x00'
        
        # DHCP ARCHITECTURE GUARD: Force absolute 0.0.0.0 clearing when DHCP initialization sequence triggers
        local_ip = "0.0.0.0" if dhcp_status == 1 else cfg_manager.get("local_ip", "192.168.1.20")
        subnet_mask = "0.0.0.0" if dhcp_status == 1 else cfg_manager.get("subnet_mask", "255.255.255.0")
        gateway = "0.0.0.0" if dhcp_status == 1 else cfg_manager.get("gateway", "192.168.1.1")
        
        self.uart.write(b'\x57\xab\x11' + self._ip_to_bytes(local_ip)); time.sleep(0.05)
        self.uart.write(b'\x57\xab\x12' + self._ip_to_bytes(subnet_mask)); time.sleep(0.05)
        self.uart.write(b'\x57\xab\x13' + self._ip_to_bytes(gateway)); time.sleep(0.05)
        self.uart.write(b'\x57\xab\x33' + dhcp_val); time.sleep(0.05)
        
        l_port = int(cfg_manager.get("local_port", 5000))
        self.uart.write(b'\x57\xab\x14' + l_port.to_bytes(2, "little")); time.sleep(0.05)
        
        self.uart.write(b'\x57\xab\x15' + self._ip_to_bytes(cfg_manager.get("target_ip", "192.168.100.70"))); time.sleep(0.05)
        t_port = int(cfg_manager.get("target_port", 3000))
        self.uart.write(b'\x57\xab\x16' + t_port.to_bytes(2, "little")); time.sleep(0.05)
        
        # Enforce default TCP Client operating mode profile layout (0x01)
        self.uart.write(b'\x57\xab\x10\x01'); time.sleep(0.05)
        
        # Sync runtime operating speed registers parameters with the target project execution limits
        self.uart.write(b'\x57\xab\x21' + int(self.working_baudrate).to_bytes(4, "little")); time.sleep(0.05)
        
        self._exit_config_and_save()