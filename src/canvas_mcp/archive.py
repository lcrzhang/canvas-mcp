"""Look inside a zip without unpacking it anywhere.

Everything that knows what a zip is lives here, the way `extract.py` is the
only module that knows what a PDF is.

**Nothing is written to disk.** A member is read into memory, bounded, and
returned. That is what makes a member called `../../../etc/passwd` a string in
a listing and nothing more: path traversal needs somebody to create a file, and
this never does.

**The bounds do not trust the archive.** A zip states the uncompressed size of
each member in its own header, and whoever built the archive wrote that header.
So the limit is applied to what actually comes out of the decompressor rather
than to what the central directory claims — a header saying "4 KB" in front of
a gigabyte of zeroes is the whole trick.

**Nothing recurses.** A zip inside a zip is listed and not opened. One archive
is a convenience for a student; a chain of them is a way to spend memory.
"""

import io
import zipfile
from typing import NamedTuple

# Enough for a homework template, a reader with its figures, or a code
# skeleton. An archive with more than this is listed up to the limit and says
# how many it really holds, rather than being refused — knowing what is in
# there is still useful.
MAX_MEMBERS = 200

# What one member may weigh once decompressed. Generous for source and far
# under what a zip bomb needs to be interesting.
MAX_MEMBER_BYTES = 5_000_000


class ArchiveError(Exception):
    """Raised when an archive cannot be read, with the reason a person needs."""


class Member(NamedTuple):
    """One entry, with the size the archive claims for it.

    `size` is the declared uncompressed size, which is worth showing and not
    worth trusting — see the module docstring. Nothing decides anything on it.
    """

    name: str
    size: int


def _open(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"This file is not a readable zip: {exc}") from exc


def members(data: bytes) -> tuple[list[Member], int]:
    """The entries, capped at `MAX_MEMBERS`, and how many there really are.

    Directories are left out: they are structure rather than content, and a
    model offered one would have nothing to do with it.
    """
    with _open(data) as archive:
        entries = [info for info in archive.infolist() if not info.is_dir()]
    listed = [Member(info.filename, info.file_size) for info in entries[:MAX_MEMBERS]]
    return listed, len(entries)


def read_member(data: bytes, name: str) -> bytes:
    """One member's bytes, refusing one that does not stop at the limit."""
    with _open(data) as archive:
        try:
            info = archive.getinfo(name)
        except KeyError:
            raise ArchiveError(
                f"There is no {name} in this archive. Read the archive without "
                "a member to see what it holds."
            ) from None
        if info.is_dir():
            raise ArchiveError(f"{name} is a folder in this archive, not a file.")
        try:
            with archive.open(info) as member:
                # One byte past the limit, so the limit can be recognised as
                # exceeded rather than inferred from a body that stops exactly
                # at it.
                body = member.read(MAX_MEMBER_BYTES + 1)
        except RuntimeError as exc:
            # What zipfile raises for an encrypted member.
            raise ArchiveError(
                f"{name} is encrypted, and this server has no password for it."
            ) from exc
        except zipfile.BadZipFile as exc:
            raise ArchiveError(f"{name} cannot be read out of this zip: {exc}") from exc

    if len(body) > MAX_MEMBER_BYTES:
        raise ArchiveError(
            f"{name} is over {MAX_MEMBER_BYTES // 1_000_000} MB unpacked, which "
            "is more than this server will read out of an archive."
        )
    return body
