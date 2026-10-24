"""Git-only secret output. Never expose this helper as an MCP tool."""

import os
import sys
from urllib.parse import urlsplit

from tum_mcp.credentials import Vault
from tum_mcp.settings import Provider, find_account


def main() -> None:
    if sys.argv[1:] != ["get"]:
        return
    account_id = os.environ.get("TUM_MCP_GIT_ACCOUNT")
    if not account_id:
        return
    account = find_account(account_id, Provider.ARTEMIS)
    fields = dict(line.split("=", 1) for line in sys.stdin.read(8192).splitlines() if "=" in line)
    for credential in Vault().load(account).repositories:
        target = urlsplit(credential.url)
        if (
            fields.get("protocol") == "https"
            and fields.get("host") == target.netloc
            and fields.get("path") == target.path.lstrip("/")
        ):
            username = credential.username.get_secret_value()
            password = credential.password.get_secret_value()
            if any(character in username + password for character in "\r\n"):
                return
            sys.stdout.write(f"username={username}\npassword={password}\n\n")
            return


if __name__ == "__main__":
    main()
