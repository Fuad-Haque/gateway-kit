"""Exception hierarchy. The CLI maps these to exit codes."""


class GatewayKitError(Exception):
    """Base class for all expected, user-facing errors."""


class ValidationError(GatewayKitError, ValueError):
    """Input data is malformed or violates a rule."""


class InfeasibleError(GatewayKitError):
    """Inputs are valid but no solution satisfies the constraints."""
