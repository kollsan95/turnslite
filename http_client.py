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
        Send a barcode string to the remote server via an HTTP GET request.

        The method constructs a raw HTTP/1.1 request, writes it to the UART,
        then aggregates the response until a short inter‑byte timeout indicates
        the end of the transmission.

        :param barcode: The scanned code to be sent (appended to the API path).
        :return: True if the server responded with a positive verdict (allowed),
                 False otherwise (timeout, parsing error, or negative response).
        """
        # --- 1. Build the HTTP GET request ----------------------------------
        raw_path = self.cfg.get("api_path", "/api/data")
        target_ip = self.cfg.get("target_ip", "192.168.100.70")
        target_port = self.cfg.get("target_port", 80)

        # Ensure the API path starts with a slash
        api_path = raw_path if raw_path.startswith("/") else "/" + raw_path

        # Build Host header: include port only if non‑standard (not 80)
        host_header = f"{target_ip}:{target_port}" if int(target_port) != 80 else target_ip

        # Raw HTTP/1.1 GET request with "Connection: close" – server will close the socket
        # after sending the response, which makes the end of data easy to detect.
        http_packet = (
            f"GET {api_path}/{barcode} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Connection: close\r\n\r\n"
        )

        # --- 2. Send the request --------------------------------------------
        try:
            self.driver.uart.write(http_packet.encode("utf-8"))
        except Exception:
            # Write failed (e.g., UART not ready, disconnected). Return False silently.
            return False

        # --- 3. Receive and aggregate the response -------------------------
        # Timing strategy:
        # - Total timeout for first byte: 3 seconds.
        # - Once data starts arriving, wait for a 100 ms gap between bytes.
        #   This gap indicates the end of transmission (since the server
        #   closes the connection after sending the full response).
        start_time = time.monotonic()
        response_data = b""
        last_data_time = start_time  # last time a byte was received

        while True:
            # How many bytes are waiting in the UART receive buffer?
            in_waiting = self.driver.uart.in_waiting

            if in_waiting > 0:
                # Read all available bytes at once (non‑blocking because we check in_waiting first)
                chunk = self.driver.uart.read(in_waiting)
                if chunk:
                    response_data += chunk
                    last_data_time = time.monotonic()
            else:
                if len(response_data) == 0:
                    # No data received yet – check total timeout (3 seconds)
                    if (time.monotonic() - start_time) > 3.0:
                        return False  # Complete timeout: no response at all
                    time.sleep(0.01)  # Short delay to avoid busy looping
                else:
                    # Data has arrived, but now the line is idle.
                    # If the idle period exceeds 100 ms, we consider the transmission finished.
                    if (time.monotonic() - last_data_time) > 0.10:
                        break
                    time.sleep(0.005)  # Very short sleep while waiting for more bytes

        # --- 4. Parse the HTTP response -------------------------------------
        if not response_data:
            return False  # No data received after timeout

        try:
            # Decode the raw bytes to a UTF-8 string (ignore any non‑UTF characters)
            full_text = response_data.decode("utf-8", "ignore")
            # Extract the HTTP body (everything after the first blank line)
            json_body = ResponseParser.extract_http_body(full_text)
            # Parse the verdict (true/false) from the JSON body
            allowed = ResponseParser.parse_verdict(json_body)
            return allowed
        except Exception:
            # Parsing error (malformed HTTP, invalid JSON, etc.)
            return False