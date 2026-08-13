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
