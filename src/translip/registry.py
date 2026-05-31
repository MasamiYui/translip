"""Generic backend registry shared across translip domains.

A :class:`BackendRegistry` maps a backend *identifier* (plus optional aliases)
to a factory callable and a :class:`BackendInfo` descriptor. Domains such as
dubbing (TTS), translation and diarization each own one registry instance and
register their backends declaratively via the :meth:`BackendRegistry.register`
decorator. Every dispatch site then resolves through the registry instead of
re-implementing an ``if/elif`` chain, so adding a backend is a single
registration site.

Factories take explicit keyword arguments (e.g. ``device``,
``worker_count_hint``) and are expected to lazily import their heavy
implementation module, keeping model runtimes off the import path until a
backend is actually constructed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

T = TypeVar("T")

Factory = Callable[..., T]


@dataclass(frozen=True, slots=True)
class BackendInfo:
    """Static, declarative description of a registered backend.

    ``metadata`` carries capability facts (e.g.
    ``supports_parallel_workers`` / ``supports_reference_retry``) that callers
    read instead of string-matching the backend name.
    """

    identifier: str
    summary: str = ""
    requires_network: bool = False
    requires_reference_audio: bool = False
    aliases: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


class BackendRegistry(Generic[T]):
    """A name -> (factory, info) registry for a single backend domain."""

    def __init__(self, domain: str) -> None:
        self.domain = domain
        self._factories: dict[str, Factory[T]] = {}
        self._infos: dict[str, BackendInfo] = {}
        self._aliases: dict[str, str] = {}

    def register(
        self,
        identifier: str,
        *,
        summary: str = "",
        requires_network: bool = False,
        requires_reference_audio: bool = False,
        aliases: tuple[str, ...] = (),
        metadata: dict[str, object] | None = None,
    ) -> Callable[[Factory[T]], Factory[T]]:
        """Decorator registering ``identifier`` with its factory + metadata."""

        info = BackendInfo(
            identifier=identifier,
            summary=summary,
            requires_network=requires_network,
            requires_reference_audio=requires_reference_audio,
            aliases=tuple(aliases),
            metadata=dict(metadata or {}),
        )

        def decorator(factory: Factory[T]) -> Factory[T]:
            if identifier in self._factories:
                raise ValueError(
                    f"backend {identifier!r} already registered in {self.domain!r}"
                )
            self._factories[identifier] = factory
            self._infos[identifier] = info
            for alias in info.aliases:
                self._aliases[alias] = identifier
            return factory

        return decorator

    def resolve(self, name: str) -> str:
        """Resolve ``name`` (identifier or alias) to a canonical identifier."""

        if name in self._factories:
            return name
        if name in self._aliases:
            return self._aliases[name]
        raise KeyError(f"unknown {self.domain} backend: {name!r}")

    def create(self, name: str, **kwargs: object) -> T:
        """Build a backend instance by ``name`` (identifier or alias)."""

        identifier = self.resolve(name)
        return self._factories[identifier](**kwargs)

    def get_info(self, name: str) -> BackendInfo:
        """Return the :class:`BackendInfo` for ``name`` (identifier or alias)."""

        identifier = self.resolve(name)
        return self._infos[identifier]

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and (
            name in self._factories or name in self._aliases
        )

    def identifiers(self) -> list[str]:
        """Canonical identifiers in registration order."""

        return list(self._factories.keys())

    def infos(self) -> list[BackendInfo]:
        """All registered :class:`BackendInfo` descriptors."""

        return list(self._infos.values())


__all__ = ["BackendRegistry", "BackendInfo"]
