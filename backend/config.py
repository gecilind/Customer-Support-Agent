from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import (
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    supabase_db_url: str = Field(alias="SUPABASE_DB_URL")
    openai_api_key: str = Field(alias="OPENAI_KEY")
    openai_chat_model: str = Field(default="gpt-4o-mini")
    # Declared so OPENAI_EMBEDDING_MODEL in .env validates; embedding calls stay hardcoded in EmbeddingService.
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    openai_realtime_model: str = Field(default="gpt-4o-realtime-preview")

    jira_base_url: str = Field(alias="JIRA_BASE_URL")
    jira_email: str = Field(alias="JIRA_EMAIL")
    jira_api_token: str = Field(alias="JIRA_API_TOKEN")
    jira_project_key: str = Field(alias="JIRA_PROJECT_KEY")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: InitSettingsSource,
        env_settings: EnvSettingsSource,
        dotenv_settings: DotEnvSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)


def get_settings() -> Settings:
    return Settings()
