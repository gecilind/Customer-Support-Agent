class AppError(Exception):
    """Base application exception."""


class IngestionError(AppError):
    """Raised when manual ingestion fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class JiraAPIError(AppError):
    """Raised when Jira REST API call fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ZendeskAPIError(AppError):
    """Raised when Zendesk REST API call fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
