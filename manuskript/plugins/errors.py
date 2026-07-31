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
