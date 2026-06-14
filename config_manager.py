# ============================================================================
# File: config_manager.py
# Role: Abstract storage engine and runtime memory parameter manager.
# Description: Parses settings stored in standard JSON files and handles
#              partial merges, string normalizations, and network payload validations.
# ============================================================================

try:
    import json
except ImportError:
    import ujson as json
import os

class ConfigManager:
    def __init__(self, filepath="settings.json"):
        """
        Initializes the configuration system mapping file path locations
        and triggers the automatic baseline profile reading engine.
        """
        self.filepath = filepath
        self.settings = {}
        self.load_config()

    def load_config(self):
        """
        Looks for the local parameters file on flash memory. Loads it if found,
        otherwise safely initializes defaults in memory to prevent crash loops.
        """
        file_exists = False
        try:
            os.stat(self.filepath)
            file_exists = True
        except OSError:
            file_exists = False

        if not file_exists:
            self._create_default_config()
            return

        try:
            with open(self.filepath, "r") as f:
                raw_data = json.load(f)
            self.settings = {str(k).strip().lower(): v for k, v in raw_data.items()}
        except Exception:
            self._create_default_config()

    def get(self, key, default=None):
        """
        Extracts values from the working properties dictionary safely.
        Normalizes keys to lower-case and returns default fallbacks if absent.
        """
        return self.settings.get(str(key).strip().lower(), default)

    def _validate_ip(self, ip_str: str) -> bool:
        """
        Validates structure for user provided network interface fields.
        Ensures string matches 4 oktets bound strictly between 0 and 255.
        """
        try:
            parts = str(ip_str).strip().split('.')
            if len(parts) != 4:
                return False
            return all(0 <= int(part) <= 255 for part in parts)
        except Exception:
            return False

    def validate_and_merge(self, json_str: str) -> bool:
        """
        Parses administrator updates via partial JSON tokens.
        Validates IP formats and string shapes, then runs non-destructive field merges.
        """
        try:
            incoming_data = json.loads(json_str)
            clean_incoming = {str(k).strip().lower(): v for k, v in incoming_data.items()}
        except Exception:
            return False

        for key in ("admin_code", "admin_pass"):
            if key in clean_incoming:
                if str(clean_incoming[key]).strip() == "":
                    return False

        future_dhcp = int(clean_incoming.get("dhcp", self.get("dhcp", 1)))
        if future_dhcp == 0:
            for key in ("local_ip", "subnet_mask", "gateway"):
                val_to_check = clean_incoming.get(key, self.get(key))
                if val_to_check and not self._validate_ip(val_to_check):
                    return False
                        
        if "target_ip" in clean_incoming and not self._validate_ip(clean_incoming["target_ip"]):
            return False

        for key, val in clean_incoming.items():
            if key in self.settings:
                if isinstance(self.settings[key], int):
                    self.settings[key] = int(val)
                else:
                    self.settings[key] = str(val)
            else:
                self.settings[key] = val

        return self._save_to_flash()

    def _save_to_flash(self) -> bool:
        """
        Serializes current data structures back into filesystem FAT blocks.
        Gracefully intercepts system locks if storage mount states are restricted.
        """
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.settings, f)
            return True
        except OSError:
            return True 
        except Exception:
            return False

    def _create_default_config(self):
        """
        Generates standard baseline default network configurations, ports,
        and access controls into working memory structures.
        """
        self.settings = {
            "uart_tx": "GP20", "uart_rx": "GP21", "pin_cfg": "GP18", "pin_rst": "GP19",
            "dhcp": 1, "local_ip": "0.0.0.0", "subnet_mask": "255.255.255.0",
            "gateway": "192.168.1.1", "target_ip": "192.168.1.10", "target_port": 3000,
            "baudrate": 115200, "api_path": "/api/v1", "admin_code": "admin", "admin_pass": "12345"
        }
        self._save_to_flash()