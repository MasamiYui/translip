class VideoVoiceSeparateError(RuntimeError):
    """Base error for the project."""


class DependencyError(VideoVoiceSeparateError):
    """Raised when a required external dependency is missing."""


class FFmpegError(VideoVoiceSeparateError):
    """Raised when ffmpeg or ffprobe fails."""


class BackendUnavailableError(VideoVoiceSeparateError):
    """Raised when a requested separation backend cannot run."""

