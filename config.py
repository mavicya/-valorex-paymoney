from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_IDS: list[int]

    DB_URL: str
    REDIS_URL: str

    MIN_ACCOUNT_AGE_DAYS: int = 14

    # VIP — Stars
    VIP_PRICE_1D_STARS: int = 25
    VIP_PRICE_7D_STARS: int = 100
    VIP_PRICE_30D_STARS: int = 300

    # VIP — UAH (balance)
    VIP_PRICE_1D_UAH: float = 25.0
    VIP_PRICE_7D_UAH: float = 90.0
    VIP_PRICE_30D_UAH: float = 250.0

    model_config = {"env_file": ".env"}


settings = Settings()

# Зручна таблиця тарифів — використовується у VIP-сервісі та клавіатурах
VIP_PLANS: dict[int, dict] = {
    1:  {"label": "1 день",  "stars": settings.VIP_PRICE_1D_STARS,  "uah": settings.VIP_PRICE_1D_UAH},
    7:  {"label": "7 днів",  "stars": settings.VIP_PRICE_7D_STARS,  "uah": settings.VIP_PRICE_7D_UAH},
    30: {"label": "30 днів", "stars": settings.VIP_PRICE_30D_STARS, "uah": settings.VIP_PRICE_30D_UAH},
}
