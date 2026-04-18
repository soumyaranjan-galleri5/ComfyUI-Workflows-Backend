"""Custom exceptions for workflow processing with user-friendly error messages."""


class WorkflowError(Exception):
    """Base exception for workflow-related errors."""
    def __init__(self, message: str, user_message: str = None):
        self.message = message  # Technical message (for logging)
        self.user_message = user_message or message  # User-friendly message
        super().__init__(self.message)


class InvalidURLError(WorkflowError):
    """Raised when URL is malformed or has invalid protocol."""
    def __init__(self, url: str, reason: str = None):
        technical = f"Invalid URL: {url[:100]}. {reason or 'Invalid format'}"
        user_friendly = "Invalid URL: Only HTTPS URLs are supported"
        super().__init__(technical, user_friendly)


class FileValidationError(WorkflowError):
    """Raised when file validation fails (type mismatch, corruption, etc)."""
    def __init__(self, filename: str, reason: str):
        technical = f"File validation failed for '{filename}': {reason}"
        user_friendly = f"Invalid file: {reason}"
        super().__init__(technical, user_friendly)


class FileTypeMismatchError(WorkflowError):
    """Raised when file content doesn't match declared extension."""
    def __init__(self, filename: str, expected: str, actual: str):
        technical = f"File type mismatch for '{filename}': expected {expected}, got {actual}"
        user_friendly = "Invalid file: Content doesn't match file extension"
        super().__init__(technical, user_friendly)


class ImageValidationError(WorkflowError):
    """Raised when image validation fails (dimensions, corruption, etc)."""
    def __init__(self, reason: str):
        technical = f"Image validation failed: {reason}"
        user_friendly = f"Invalid image: {reason}"
        super().__init__(technical, user_friendly)


class VideoValidationError(WorkflowError):
    """Raised when video validation fails (frame count, format, etc)."""
    def __init__(self, reason: str):
        technical = f"Video validation failed: {reason}"
        user_friendly = f"Invalid video: {reason}"
        super().__init__(technical, user_friendly)


class DownloadError(WorkflowError):
    """Raised when URL download fails."""
    def __init__(self, url: str, reason: str):
        technical = f"Failed to download {url}: {reason}"
        user_friendly = "Failed to download file from URL"
        super().__init__(technical, user_friendly)


class WorkflowExecutionError(WorkflowError):
    """Raised when workflow execution fails."""
    def __init__(self, reason: str):
        technical = f"Workflow execution failed: {reason}"
        user_friendly = "Workflow processing failed"
        super().__init__(technical, user_friendly)
