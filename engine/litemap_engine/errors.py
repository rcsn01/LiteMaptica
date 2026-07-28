class EngineError(Exception):
    """An expected error safe to return over JSON-RPC."""

    code = -32000


class InvalidProject(EngineError):
    code = -32010


class ValidationError(EngineError):
    code = -32020


class CapabilityUnavailable(EngineError):
    code = -32030
