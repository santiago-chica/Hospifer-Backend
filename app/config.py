from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Provisionales:
    # sqlite+aiosqlite:///./app.db
    # postgresql+psycopg://postgres:password@localhost:5432/mydb
    
    database_url: str = 'sqlite+aiosqlite:///./app.db'
    secret_key: str
    environment: Literal['development', 'production'] = 'development'
    access_token_expire_minutes: int = 30
    initial_admin_username: str = 'admin'
    initial_admin_password: str | None = None
    cors_origins: list[str] = ['http://localhost:5173', 'http://127.0.0.1:5173']

    @model_validator(mode='after')
    def validate_production_security(self):
        if self.environment == 'production':
            if len(self.secret_key.encode('utf-8')) < 32:
                raise ValueError('SECRET_KEY must contain at least 32 bytes in production.')
            if not self.initial_admin_password or len(self.initial_admin_password.encode('utf-8')) < 12:
                raise ValueError('Set INITIAL_ADMIN_PASSWORD to at least 12 bytes in production.')
            if len(self.initial_admin_password.encode('utf-8')) > 72:
                raise ValueError('INITIAL_ADMIN_PASSWORD cannot exceed 72 bytes.')
        if self.access_token_expire_minutes <= 0:
            raise ValueError('ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero.')
        return self
    
    model_config = SettingsConfigDict(env_file='.env')

settings = Settings()