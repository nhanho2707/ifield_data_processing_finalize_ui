class IFieldError(Exception):
    """Base class for errors whose message is meant to be shown to the user as-is."""


class ConfigError(IFieldError):
    """config.json is missing, malformed or inconsistent with the source files."""


class SourceError(IFieldError):
    """A source file (CSV, XML, update_data.csv) is missing or unreadable."""


class ProcessingError(IFieldError):
    """A processing step failed (DMS job, data insertion, ...)."""


class Cancelled(IFieldError):
    """The user cancelled the running job."""
