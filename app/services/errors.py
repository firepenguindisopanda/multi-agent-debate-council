class ServiceError(Exception):
    """Base class for business-rule failures, carrying a user-presentable message."""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidInputError(ServiceError):
    status_code = 422


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class ProviderNotConfiguredError(ServiceError):
    status_code = 503
