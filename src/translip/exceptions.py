class TranslipError(RuntimeError):
    """Base error for the project."""


class DependencyError(TranslipError):
    """Raised when a required external dependency is missing."""


class FFmpegError(TranslipError):
    """Raised when ffmpeg or ffprobe fails."""


class BackendUnavailableError(TranslipError):
    """Raised when a requested separation backend cannot run."""

