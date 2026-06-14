# ============================================================================
# File: response_parser.py
# Role: Independent network layer response utility.
# Description: Isolates HTTP payload text boundaries and strictly validates
#              the boolean 'allowed' flag structural schema within JSON bodies.
# ============================================================================

import json

class ResponseParser:
    """
    A collection of static methods to extract and interpret server responses.
    Handles both properly formatted HTTP+JSON and simple fallback text formats.
    """

    @staticmethod
    def extract_http_body(full_text: str) -> str:
        """
        Locates the root JSON token index via bracket mapping heuristics.

        This method tries to extract the JSON body from an HTTP response.
        It handles two common patterns:
        1. A JSON object starting with '{' – returns everything from that character.
        2. If no '{' is found, it looks for the double-CRLF (headers/body separator)
           and returns everything after it, stripped.

        :param full_text: The raw HTTP response as a string (may include headers).
        :return: A string containing the extracted JSON body, or the cleaned original text.
        """
        if not full_text:
            return ""

        # Look for the start of a JSON object (most reliable for structured data)
        start_idx = full_text.find("{")
        if start_idx != -1:
            # Found a '{' – assume the JSON body starts here and includes all remaining text
            return full_text[start_idx:].strip()

        # If no '{' found, try to split using the standard HTTP header/body delimiter "\r\n\r\n"
        if "\r\n\r\n" in full_text:
            # Take everything after the blank line (the body)
            return full_text.split("\r\n\r\n", 1)[1].strip()

        # If all else fails, return the whole text stripped (maybe it's just a simple string)
        return full_text.strip()

    @staticmethod
    def parse_verdict(json_body: str) -> bool:
        """
        Evaluates the status of the 'allowed' data attribute.
        Maps assertions strictly to Boolean True or False.

        The method first tries to parse the input as strict JSON.
        If that fails, it falls back to a simple text search for the pattern "allowed:true".

        Recognized true values: True (boolean) or the string "true".
        Recognized false values: False (boolean) or the string "false".
        Any other value (or missing key) defaults to False.

        :param json_body: The extracted body string (expected to contain a JSON object
                          or at least a simple key-value pair).
        :return: True if the response indicates access should be granted, False otherwise.
        """
        if not json_body:
            return False

        # --- Step 1: Standard JSON parsing ---------------------------------
        try:
            data = json.loads(json_body)
            # Expect the top-level structure to be a dictionary
            if isinstance(data, dict):
                allowed = data.get("allowed", None)
                # Explicitly check for boolean True or the string "true"
                if allowed is True or allowed == "true":
                    return True
                # Explicitly check for boolean False or the string "false"
                if allowed is False or allowed == "false":
                    return False
        except Exception:
            # JSON parsing failed (malformed JSON, non-JSON body) – proceed to fallback
            pass

        # --- Step 2: Fallback literal scan for simple "allowed:true" pattern ---
        # Remove whitespace, quotes (both double and single), and convert to lowercase
        clean_text = json_body.replace(" ", "").replace('"', '').replace("'", "").lower().strip()
        if "allowed:true" in clean_text:
            return True

        # No positive indication – deny access by default
        return False