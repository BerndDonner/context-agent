class ContextAgentError(Exception):
    """Base class for expected context-agent failures."""


class ConfigurationError(ContextAgentError):
    """The job configuration or job directory is invalid."""


class RemoteAgentError(ContextAgentError):
    """The OpenAI-hosted agent session failed."""


class ArtifactError(ContextAgentError):
    """Expected output artifacts could not be retrieved."""


class NogoError(ContextAgentError):
    """A no-go checker could not be loaded or executed."""
