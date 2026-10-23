import json
import sys

from runtime_setup import ensure_runtime, root


def main() -> int:
    result = ensure_runtime(root, repair="--repair" in sys.argv)
    print(
        json.dumps(
            {
                "changed": result.changed,
                "timings": result.timings,
                "keyring_error": result.keyring_error,
            }
        )
    )
    return 2 if result.keyring_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
