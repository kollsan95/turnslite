# ============================================================================
# File: http_client.py
# Role: Application layer network request formatter and stream manager.
# Description: Generates standard HTTP/1.1 GET packets over raw TCP sockets,
#              forces server connection termination, and aggregates responses.
# ============================================================================

import time
from response_parser import ResponseParser


class NetworkHttpClient:
    """Simple HTTP client that sends barcodes via GET requests using a CH9120 UART driver."""

    def __init__(self, driver, config_manager):
        """
        Initialize the HTTP client.

        :param driver: CH9120Driver instance (provides UART access to the network chip).
        :param config_manager: ConfigManager instance (holds target IP, port, API path).
        """
        self.driver = driver
        self.cfg = config_manager

    def send_barcode(self, barcode: str) -> bool:
        """
        Send a barcode to the server and wait for the full HTTP response.
        Uses Content-Length header to determine exactly how many bytes to read.
        """
        # --- 1. Build HTTP request ------------------------------------------
        raw_path = self.cfg.get("api_path", "/api/data")
        target_ip = self.cfg.get("target_ip", "192.168.100.70")
        target_port = self.cfg.get("target_port", 80)

        api_path = raw_path if raw_path.startswith("/") else "/" + raw_path
        host_header = f"{target_ip}:{target_port}" if int(target_port) != 80 else target_ip

        http_packet = (
            f"GET {api_path}/{barcode} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Connection: close\r\n\r\n"
        )

        # --- 2. Flush UART buffer before sending ----------------------------
        while self.driver.uart.in_waiting:
            _ = self.driver.uart.read(self.driver.uart.in_waiting)

        # --- 3. Send the request --------------------------------------------
        try:
            self.driver.uart.write(http_packet.encode("utf-8"))
        except Exception:
            return False

        # --- 4. Read response (headers + body) ------------------------------
        response_data = b""
        start_time = time.monotonic()
        total_timeout = 10.0
        header_found = False
        content_length = None
        header_end_pos = -1

        # Read all data until we have the full response
        while True:
            # Global timeout protection
            if (time.monotonic() - start_time) > total_timeout:
                print(f"[TIMEOUT] Total timeout exceeded")
                return False

            if self.driver.uart.in_waiting:
                chunk = self.driver.uart.read(self.driver.uart.in_waiting)
                if chunk:
                    response_data += chunk

                    # Try to find headers and Content-Length if not yet found
                    if not header_found:
                        if b"\r\n\r\n" in response_data:
                            header_found = True
                            header_end_pos = response_data.find(b"\r\n\r\n") + 4
                            
                            # Parse Content-Length from headers
                            header_part = response_data[:header_end_pos]
                            for line in header_part.split(b"\r\n"):
                                if line.lower().startswith(b"content-length:"):
                                    try:
                                        content_length = int(line.split(b":")[1].strip())
                                    except ValueError:
                                        content_length = None
                                    break
                            
                            # If Content-Length found, calculate how much body we need
                            if content_length is not None:
                                body_received = len(response_data) - header_end_pos
                                # If we already have the full body, we can break
                                if body_received >= content_length:
                                    break
            else:
                # No data available – short sleep to avoid busy loop
                time.sleep(0.005)

            # If we have headers and Content-Length, check if we got the full body
            if header_found and content_length is not None:
                body_received = len(response_data) - header_end_pos
                if body_received >= content_length:
                    break

        # --- 5. Debug output ------------------------------------------------
        print(f"[DEBUG] Total received: {len(response_data)} bytes")
        if content_length is not None:
            print(f"[DEBUG] Content-Length: {content_length} bytes")
            body_received = len(response_data) - header_end_pos
            print(f"[DEBUG] Body received: {body_received} bytes")
        print(response_data)

        # --- 6. Parse and return -------------------------------------------
        if not response_data:
            return False

        try:
            full_text = response_data.decode("utf-8", "ignore")
            json_body = ResponseParser.extract_http_body(full_text)
            allowed = ResponseParser.parse_verdict(json_body)
            return allowed
        except Exception as e:
            print(f"[ERROR] Parse error: {e}")
            return False