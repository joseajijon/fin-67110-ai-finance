"""Read the lab credentials from .env without exposing the full API key."""

from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    """Load simple KEY=VALUE lines from an environment file."""
    values: dict[str, str] = {}

    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid line {line_number} in {path.name}")

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def main() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        raise SystemExit("Missing .env file. Create it beside check_env.py.")

    env = load_env(env_path)
    api_key = env.get("API_KEY", "")
    user_agent = env.get("SEC_USER_AGENT", "")

    if not api_key:
        raise SystemExit("API_KEY is missing from .env.")
    if not user_agent:
        raise SystemExit("SEC_USER_AGENT is missing from .env.")

    print(f"{api_key[:4]}...")
    print(user_agent)


if __name__ == "__main__":
    main()
