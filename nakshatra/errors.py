"""Typed errors. Codes come from the API Contract §6 catalogue."""


class NakshatraError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message
