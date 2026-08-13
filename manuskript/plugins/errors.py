class PluginError(Exception):
    """Base class for actionable plugin failures."""


class PluginManifestError(PluginError):
    pass


class PluginCompatibilityError(PluginError):
    pass


class PluginLoadError(PluginError):
    pass


class PluginRegistrationError(PluginError):
    pass


class PluginScopeError(PluginError):
    """A plugin reached past the contributions it owns."""


class PluginValueError(PluginError, ValueError):
    """A value cannot be represented by the portable Plugin API model."""


class PluginProtocolError(PluginError):
    """An external plugin violated RPC protocol framing or message rules."""


class PluginProcessError(PluginError):
    """An external plugin process could not start or remain available."""


class PluginRequestTimeout(PluginProcessError, TimeoutError):
    """An external plugin did not answer within the operation deadline."""


class PluginRemoteError(PluginError):
    """A valid JSON-RPC error returned by the plugin."""

    def __init__(self, code, message, data=None):
        super().__init__("Remote plugin error {}: {}".format(code, message))
        self.code = code
        self.message = str(message)
        self.data = data


class PluginConflictError(PluginError):
    """A remote write targeted a stale project or resource revision."""

    def __init__(self, message, data=None):
        super().__init__(message)
        self.data = dict(data or {})
