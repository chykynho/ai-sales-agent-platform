class ToolExecutionError(RuntimeError):
    def __init__(self, message: str, *, code: str = "tool_execution_error") -> None:
        super().__init__(message)
        self.code = code
