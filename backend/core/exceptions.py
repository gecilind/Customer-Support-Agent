class AppError(Exception):
    """Base application exception."""


class IngestionError(AppError):
    """Raised when manual ingestion fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
