r"""Replace the Canvas token in every MCP client config, but only if Canvas accepts it.

Run it when the old token expires -- Canvas personal access tokens last at most
90 days:

    Windows   tools\set-token.cmd
    macOS     tools/set-token.sh

The token is typed at a hidden prompt, never passed as an argument, and never
printed back. An invalid token is rejected before anything is written, so a
failed paste leaves the working config in place instead of replacing it with
something that only fails later, inside a client, as a bare "failed to connect".

Standard library only: this runs on a machine where the venv may not be built
yet, and the repository adds no dependency for a helper script.
"""

import getpass
import json
import os
import shutil
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("CANVAS_BASE_URL", "https://canvas.uva.nl").rstrip("/")


DESKTOP_CONFIG = "claude_desktop_config.json"


def client_configs() -> list[tuple[str, Path]]:
    """The config files that hold an MCP server entry, per platform."""
    home = Path.home()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or home / "AppData" / "Roaming"
        desktop = Path(appdata) / "Claude" / DESKTOP_CONFIG
    elif sys.platform == "darwin":
        desktop = home / "Library" / "Application Support" / "Claude" / DESKTOP_CONFIG
    else:
        desktop = home / ".config" / "Claude" / DESKTOP_CONFIG
    return [("Claude Desktop", desktop), ("Claude Code", home / ".claude.json")]


def ssl_context() -> ssl.SSLContext:
    """Verify properly, even where SSL_CERT_FILE points at a bundle that is gone.

    Python reads SSL_CERT_FILE unconditionally, so a stale value makes every
    HTTPS call die with a bare FileNotFoundError that names no variable.
    """
    stale = os.environ.get("SSL_CERT_FILE")
    if stale and not os.path.isfile(stale):
        print(f"  note: ignoring SSL_CERT_FILE, the file is missing: {stale}")
        os.environ.pop("SSL_CERT_FILE", None)
    try:
        import truststore  # comes with the MCP stack; trusts what the OS trusts
    except ImportError:
        return ssl.create_default_context()
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def check(token: str) -> str:
    """Ask Canvas who the token belongs to. Returns a display name, or exits."""
    req = urllib.request.Request(
        BASE_URL + "/api/v1/users/self",
        headers={"Authorization": "Bearer " + token},
    )
    try:
        with urllib.request.urlopen(req, context=ssl_context(), timeout=30) as resp:
            return json.loads(resp.read()).get("name", "(no name)")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            sys.exit(
                "\nCanvas rejected this token (401 Invalid access token).\n"
                "Nothing was written.\n\n"
                f"  - Is it a token for {BASE_URL}? Another institution needs\n"
                "    CANVAS_BASE_URL set, here and in the config's env block.\n"
                "  - Was the whole value copied? Canvas shows it once only.\n"
                "  - Is it still listed under Account -> Settings ->\n"
                "    Approved Integrations, and not past its expiry?\n"
            )
        sys.exit(f"\nCanvas answered {exc.code}. Nothing was written.")
    except Exception as exc:
        sys.exit(f"\nCould not reach {BASE_URL}: {exc!r}\nNothing was written.")


def write(path: str | Path, token: str) -> str:
    """Set CANVAS_TOKEN on the canvas entry, leaving every other key untouched."""
    path = Path(path)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    entry = cfg.get("mcpServers", {}).get("canvas")
    if entry is None:
        return "no canvas entry - skipped"
    shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
    entry.setdefault("env", {})["CANVAS_TOKEN"] = token
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return "updated"


def main() -> None:
    print(f"New Canvas access token for {BASE_URL}")
    print("Make one at: Account -> Settings -> + New Access Token")
    print("(input stays hidden; paste it, then press Enter)\n")

    token = getpass.getpass("Token: ").strip()
    if not token:
        sys.exit("Nothing entered. Nothing was written.")

    print("\nChecking it against Canvas...")
    name = check(token)
    print(f"Accepted - token belongs to: {name}\n")

    wrote = False
    for label, path in client_configs():
        if not path.exists():
            print(f"  {label:16} not found - skipped")
            continue
        try:
            result = write(path, token)
            wrote = wrote or result == "updated"
            print(f"  {label:16} {result}")
        except Exception as exc:
            print(f"  {label:16} FAILED: {exc!r}")

    if not wrote:
        sys.exit("\nNo config was updated. Register the server first; see the README.")

    print("\nDone. Restart Claude Desktop completely for it to pick this up")
    print("(quit the app, not just the window). Then: claude mcp list")


if __name__ == "__main__":
    main()
