"""WordPress connection settings."""

import os
import json
import sys
import tempfile
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    url: str
    username: str
    app_password: str


CONFIG_NAMES = ("WORDPRESS_URL", "WORDPRESS_USERNAME", "WORDPRESS_APP_PASSWORD")


def user_config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".config"
    return base / "99blog-cli" / "config.env"


def _validate_url(value: str) -> str:
    url = value.rstrip("/")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ConfigError("WORDPRESS_URL is not a valid URL") from exc
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ConfigError("WORDPRESS_URL must be an HTTPS site URL, e.g. https://example.com/blog/")
    return url


def load_config() -> Config:
    # Highest priority first: environment, current-directory .env, user config,
    # then the legacy project .env. Reading files does not modify os.environ.
    sources = [
        os.environ,
        dotenv_values(Path.cwd() / ".env", interpolate=False),
        dotenv_values(user_config_path(), interpolate=False),
        dotenv_values(Path(__file__).with_name(".env"), interpolate=False),
    ]
    values = {name: next((str(source[name]).strip() for source in sources if source.get(name) is not None), "")
              for name in CONFIG_NAMES}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(f"Missing configuration: {', '.join(missing)}. Run '99blog configure' or see .env.example")
    return Config(_validate_url(values["WORDPRESS_URL"]), values["WORDPRESS_USERNAME"], values["WORDPRESS_APP_PASSWORD"])


def configure() -> Path:
    path = user_config_path()
    saved = dotenv_values(path, interpolate=False)
    try:
        default_url = str(saved.get("WORDPRESS_URL") or "")
        default_user = str(saved.get("WORDPRESS_USERNAME") or "")
        url = input(f"WordPress URL [{default_url or 'https://example.com/blog/'}]: ").strip() or default_url
        username = input(f"WordPress username [{default_user or 'required'}]: ").strip() or default_user
        password = getpass("Application password (hidden; Enter keeps saved value): ").strip()
    except EOFError as exc:
        raise ConfigError("Interactive input is required to configure WordPress") from exc
    password = password or str(saved.get("WORDPRESS_APP_PASSWORD") or "")
    missing = [name for name, value in zip(CONFIG_NAMES, (url, username, password)) if not value]
    if missing:
        raise ConfigError(f"Missing configuration: {', '.join(missing)}")
    url = _validate_url(url)
    if any("\n" in value or "\r" in value or "\x00" in value for value in (url, username, password)):
        raise ConfigError("Configuration values must be single-line text")
    data = "".join(f"{name}={json.dumps(value, ensure_ascii=False)}\n"
                   for name, value in zip(CONFIG_NAMES, (url, username, password)))
    temporary = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".config-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            os.chmod(temporary, 0o600)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ConfigError(f"Cannot save WordPress configuration: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return path
