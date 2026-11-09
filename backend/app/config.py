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

    # Job queue
    #   off    : the study stays "anonymized", nothing is analysed
    #   local  : a DUMMY worker runs inside the backend (no Docker needed)
    #   celery : the job goes to Redis; separate worker containers pick it up
    queue_mode: str = "off"
    celery_broker_url: str = "redis://localhost:6379/0"
    # Hand-over area between the zones. Folders are named by the RANDOM KEY, never by study id.
    transfer_dir: str = "./data/transfer"
    worker_secret: str = "dev-worker-secret"  # CHANGE in .env for any real deployment
    dummy_delay_seconds: float = 3.0          # makes "processing" visible in the UI


settings = Settings()
