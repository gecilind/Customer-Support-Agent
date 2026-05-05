from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import (
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_db_url: str = Field(alias="SUPABASE_DB_URL")
    openai_api_key: str = Field(alias="OPENAI_KEY")
    openai_chat_model: str = Field(default="OPENAI_CHAT_MODEL")
    # Declared so OPENAI_EMBEDDING_MODEL in .env validates; embedding calls stay hardcoded in EmbeddingService.
    openai_embedding_model: str = Field(default="OPENAI_EMBEDDING_MODEL")
    openai_realtime_model: str = Field(..., alias="OPENAI_VOICE_MODEL")

    jira_base_url: str = Field(alias="JIRA_BASE_URL")
    jira_email: str = Field(alias="JIRA_EMAIL")
    jira_api_token: str = Field(alias="JIRA_API_TOKEN")
    jira_project_key: str = Field(alias="JIRA_PROJECT_KEY")

    zendesk_subdomain: str = Field(alias="ZENDESK_SUBDOMAIN")
    zendesk_email: str = Field(alias="ZENDESK_EMAIL")
    zendesk_api_token: str = Field(alias="ZENDESK_API_TOKEN")

    zendesk_help_center_url: str = Field(
        default="https://hilfe.infleet.de",
        alias="ZENDESK_HELP_CENTER_URL",
    )
    zendesk_locale: str = Field(default="de", alias="ZENDESK_LOCALE")
    zendesk_articles_per_page: int = Field(default=100, alias="ZENDESK_ARTICLES_PER_PAGE")

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
