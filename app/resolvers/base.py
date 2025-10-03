from typing import Optional

class ResolveError(Exception):
    pass

class Resolver:
    def resolve(self, target: str) -> str:
        """Return an M3U8 URL for the provided target or raise ResolveError."""
        raise NotImplementedError
