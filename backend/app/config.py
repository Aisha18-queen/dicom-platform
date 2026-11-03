from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./dev.db"  # overridden by docker-compose
    secret_key: str = "dev-secret-change-me"
    token_minutes: int = 60
    admin_username: str = "admin"
    admin_password: str = "admin"
    upload_dir: str = "./data/uploads"
    # Upload limits (goal 5.1: validate type, size, count)
    max_files: int = 1000
    max_file_mb: int = 200
    max_total_mb: int = 1000
    # Frontend addresses allowed to call this API (CORS)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
