from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8"}

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    finnhub_api_key: str = ""

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e2b"

    watchlist: str = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,NFLX,INTC"
    max_position_size: float = 1000.0
    max_total_exposure: float = 5000.0
    risk_per_trade: float = 0.02
    cycle_interval_sec: int = 3600
    max_concurrent_positions: int = 5

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    dashboard_username: str = ""
    dashboard_password: str = ""

    use_rl_decision: bool = False

    data_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "data")

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.watchlist.split(",") if s.strip()]

    @property
    def cache_dir(self) -> Path:
        self.data_dir.joinpath("cache").mkdir(parents=True, exist_ok=True)
        return self.data_dir / "cache"

    @property
    def logs_dir(self) -> Path:
        self.data_dir.joinpath("logs").mkdir(parents=True, exist_ok=True)
        return self.data_dir / "logs"


settings = Settings()
