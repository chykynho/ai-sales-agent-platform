class ResilienceError(RuntimeError):
    """Erro base dos mecanismos de resiliência."""


class RateLimitExceeded(ResilienceError):
    pass


class CircuitOpenError(ResilienceError):
    pass


class BulkheadRejectedError(ResilienceError):
    pass
