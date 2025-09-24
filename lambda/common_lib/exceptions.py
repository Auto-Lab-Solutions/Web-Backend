"""
Common exceptions used across the application
"""


class BusinessLogicError(Exception):
    """Custom exception for business logic errors"""
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(Exception):
    """Custom exception for validation errors"""
    def __init__(self, message, field=None):
        self.message = message
        self.field = field
        super().__init__(self.message)


class PermissionError(Exception):
    """Custom exception for permission-related errors"""
    def __init__(self, message, status_code=403):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)
