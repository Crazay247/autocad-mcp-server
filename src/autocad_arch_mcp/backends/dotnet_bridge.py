"""DotNet bridge — NamedPipe length-prefix framing + IExtensionApplication stub.

Pipe protocol: 4-byte big-endian length prefix + JSON payload (utf-8).
C# side: NamedPipeServerStream with SDDL current-user-only, randomised
pipe name persisted to %LOCALAPPDATA%\\autocad-arch-mcp\\pipe_name.txt,
marshalled to doc thread via Application.DocumentManager.MdiActiveDocument.Invoke.

This is Task 8 minimal stub; full pipe client _dispatch_via_pipe is deferred
until acad host integration. Framing helpers are production-ready.
"""

from __future__ import annotations

import struct

from .base import AutoCADBackend, BackendCapabilities, CommandResult


def _frame_encode(data: bytes) -> bytes:
    """Encode bytes with 4-byte big-endian length prefix."""
    return struct.pack(">I", len(data)) + data


def _frame_decode(framed: bytes) -> bytes:
    """Decode length-prefixed frame back to payload bytes."""
    length = struct.unpack(">I", framed[:4])[0]
    return framed[4 : 4 + length]


class DotNetBridge(AutoCADBackend):
    """Stub .NET bridge — pipe pending acad host."""

    @property
    def name(self) -> str:
        return "dotnet"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(can_screenshot=True, can_plot_pdf=True, can_zoom=True)

    async def initialize(self) -> CommandResult:
        return CommandResult(ok=True, payload="dotnet init (stub, pipe pending acad)")

    async def status(self) -> CommandResult:
        return CommandResult(ok=True, payload={"backend": self.name, "pipe": "stub"})

    async def drawing_create(self, name: str | None = None) -> CommandResult:
        return CommandResult(ok=True, payload="dotnet drawing_create stub")
