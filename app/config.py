from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Provisionales:
    # sqlite+aiosqlite:///./app.db
    # postgresql+psycopg://postgres:password@localhost:5432/mydb
    
    database_url: str = 'sqlite+aiosqlite:///./app.db'
    secret_key: str
    
    model_config = SettingsConfigDict(env_file='.env')

settings = Settings()