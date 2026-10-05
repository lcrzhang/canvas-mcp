"""Looking inside a zip: what comes back, and what the bounds refuse.

The bounds are the interesting part. A zip states its own uncompressed sizes
and whoever built it wrote those numbers, so the tests that matter are the ones
where the archive lies.
"""

import io
import zipfile

import pytest

from canvas_mcp.archive import (
    MAX_MEMBER_BYTES,
    MAX_MEMBERS,
    ArchiveError,
    members,
    read_member,
)

TEMPLATE = "\\documentclass{article}\n% answer 1a here\n"


def zipped(entries: dict[str, bytes | str], **kwargs: object) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", **kwargs) as archive:  # type: ignore[arg-type]
        for name, body in entries.items():
            archive.writestr(name, body)
    return buffer.getvalue()


ARCHIVE = zipped({"tpl/template.tex": TEMPLATE, "tpl/logo.png": b"\x89PNG"})


# --- listing ---------------------------------------------------------------


def test_the_members_come_back_with_their_names_and_sizes() -> None:
    listed, total = members(ARCHIVE)
    assert total == 2
    assert [m.name for m in listed] == ["tpl/template.tex", "tpl/logo.png"]
    assert listed[0].size == len(TEMPLATE)


def test_a_folder_is_not_a_member() -> None:
    """A directory entry is structure, and a model offered one could do
    nothing with it."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("tpl/", "")
        archive.writestr("tpl/a.tex", "x")
    listed, total = members(buffer.getvalue())
    assert [m.name for m in listed] == ["tpl/a.tex"]
    assert total == 1


def test_a_huge_listing_is_capped_and_says_how_many_there_are() -> None:
    many = zipped({f"f{n}.tex": "x" for n in range(MAX_MEMBERS + 50)})
    listed, total = members(many)
    assert len(listed) == MAX_MEMBERS
    assert total == MAX_MEMBERS + 50


def test_something_that_is_not_a_zip_says_so() -> None:
    with pytest.raises(ArchiveError, match="not a readable zip"):
        members(b"%PDF-1.4 this is not a zip")


# --- reading one member ----------------------------------------------------


def test_a_member_comes_back_as_its_own_bytes() -> None:
    assert read_member(ARCHIVE, "tpl/template.tex").decode() == TEMPLATE


def test_a_member_that_is_not_there_says_how_to_find_out_what_is() -> None:
    with pytest.raises(ArchiveError, match="no tpl/missing.tex in this archive"):
        read_member(ARCHIVE, "tpl/missing.tex")


def test_a_folder_cannot_be_read_as_a_file() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("tpl/", "")
    with pytest.raises(ArchiveError, match="is a folder"):
        read_member(buffer.getvalue(), "tpl/")


def test_an_encrypted_member_says_so_rather_than_failing_obscurely() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("secret.tex", "x")
    data = bytearray(buffer.getvalue())
    # Set the encryption bit in both the local header and the central
    # directory, which is what zipfile checks before it tries to decrypt.
    for offset in (6, data.rindex(b"PK\x01\x02") + 8):
        data[offset] |= 0x01
    with pytest.raises(ArchiveError, match="encrypted"):
        read_member(bytes(data), "secret.tex")


# --- the bounds, where the archive lies ------------------------------------


def test_a_member_that_unpacks_past_the_limit_is_refused() -> None:
    """A zip bomb: a small archive whose member decompresses to far more than
    this will read. The limit is applied to what comes out of the
    decompressor, not to the size the archive declares."""
    bomb = zipped(
        {"big.tex": b"\0" * (MAX_MEMBER_BYTES + 1000)},
        compression=zipfile.ZIP_DEFLATED,
    )
    assert len(bomb) < 100_000, "the point is that the archive itself is small"
    with pytest.raises(ArchiveError, match="unpacked"):
        read_member(bomb, "big.tex")


def test_a_lying_header_does_not_get_a_member_past_the_limit() -> None:
    """`file_size` is written by whoever built the archive. Nothing decides on
    it, so rewriting it to 1 changes nothing about what is allowed through."""
    bomb = zipped(
        {"big.tex": b"\0" * (MAX_MEMBER_BYTES + 1000)},
        compression=zipfile.ZIP_DEFLATED,
    )
    with zipfile.ZipFile(io.BytesIO(bomb)) as archive:
        assert archive.getinfo("big.tex").file_size > MAX_MEMBER_BYTES
    with pytest.raises(ArchiveError, match="unpacked"):
        read_member(bomb, "big.tex")


def test_a_member_exactly_at_the_limit_is_allowed() -> None:
    at_limit = zipped(
        {"big.tex": b"x" * MAX_MEMBER_BYTES}, compression=zipfile.ZIP_DEFLATED
    )
    assert len(read_member(at_limit, "big.tex")) == MAX_MEMBER_BYTES


def test_a_traversal_name_is_only_a_name() -> None:
    """Nothing is written to disk, so `..` has nothing to escape. It is listed
    and read as the string it is."""
    nasty = zipped({"../../etc/passwd": "not really"})
    listed, _ = members(nasty)
    assert listed[0].name == "../../etc/passwd"
    assert read_member(nasty, "../../etc/passwd") == b"not really"
