"""Turn teacher-written HTML into plain text a model can be shown safely.

Assignment descriptions, announcement bodies and page content are written by
third parties and can contain text aimed at a model — see `SCOPE.md` section 6.

**This does not solve prompt injection and is not meant to.** It makes the
boundary of untrusted content visible and keeps its size bounded. The actual
defence is that this project has no write tools: there is nothing to misuse.
Anything here that reads like a security control is a mitigation, and the
README says so.

Three jobs, in order:

1. HTML becomes plain text, with links kept as readable text rather than
   dropped — a description that says "see the link" is useless without it.
2. The result is capped, with an explicit marker saying how much was cut.
3. It is wrapped in delimiters, so where the untrusted part begins and ends is
   visible rather than inferred.
"""

from html.parser import HTMLParser

MAX_CHARS = 2000

BEGIN = "--- BEGIN UNTRUSTED CONTENT"
END = "--- END UNTRUSTED CONTENT ---"

# Elements whose text is markup machinery, not content.
_DROPPED = frozenset({"script", "style", "head", "title"})
# Elements that end a line when they open or close.
_BLOCKS = frozenset(
    {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
)


class _TextExtractor(HTMLParser):
    """Collects readable text, keeping link targets."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._dropping = 0
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROPPED:
            self._dropping += 1
        elif tag in _BLOCKS:
            self.parts.append("\n")
            if tag == "li":
                self.parts.append("- ")
        elif tag == "a":
            self._href = dict(attrs).get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROPPED:
            self._dropping = max(0, self._dropping - 1)
        elif tag in _BLOCKS:
            self.parts.append("\n")
        elif tag == "a" and self._href:
            # The URL is kept as text: a description reading "see the link"
            # tells a model nothing without it.
            self.parts.append(f" ({self._href})")
            self._href = None

    def handle_data(self, data: str) -> None:
        if not self._dropping:
            self.parts.append(data)


def to_plain_text(html: str) -> str:
    """Strip markup, keep the words and the links."""
    parser = _TextExtractor()
    parser.feed(html or "")
    parser.close()
    text = "".join(parser.parts)

    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def cap(text: str, limit: int = MAX_CHARS) -> str:
    """Cut to `limit`, saying how much was cut rather than trailing off."""
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit].rstrip()}\n[truncated, {omitted} characters omitted]"


def untrusted(text: str, source: str) -> str:
    """Wrap content in a visible boundary naming where it came from.

    The delimiters are stripped out of the content first. Without that, text
    written by a third party could close the block early and have whatever
    follows read as though it came from the server rather than from them —
    which is the one thing this wrapper exists to prevent.
    """
    body = text.replace(BEGIN, "").replace(END, "")
    return f"{BEGIN} ({source}, written by a third party) ---\n{body}\n{END}"


def sanitize(html: str, source: str, limit: int = MAX_CHARS) -> str:
    """The whole pipeline: markup out, size bounded, boundary visible."""
    return untrusted(cap(to_plain_text(html), limit), source)
