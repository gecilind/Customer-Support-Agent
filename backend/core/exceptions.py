class AppError(Exception):
    """Base application exception."""


class IngestionError(AppError):
    """Raised when manual ingestion fails."""
