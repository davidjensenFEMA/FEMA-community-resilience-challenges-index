"""
Application settings loaded from environment variables.

Uses pydantic-settings for validation and type safety.
All settings are loaded from .env file in project root.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings with validation.

    All settings are loaded from .env file or environment variables.
    Environment variables take precedence over .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra fields in .env
    )

    # =============================================================================
    # API Keys
    # =============================================================================
    census_api_key: str = Field(
        default="",  # Empty default for testing
        description="Census Bureau API key (required for API calls)",
        min_length=0,
    )

    # =============================================================================
    # Data Years
    # =============================================================================
    acs_year: int = Field(
        default=2021,
        description="American Community Survey data year",
        ge=2010,
        le=2030,
    )

    cbp_year: int = Field(
        default=2020,
        description="County Business Patterns data year",
        ge=2010,
        le=2030,
    )

    naics_year: int = Field(
        default=2017,
        description="NAICS classification year",
        ge=2007,
        le=2027,
    )

    pop_year: int = Field(
        default=2020,
        description="Population estimates year",
        ge=2010,
        le=2030,
    )

    asarb_year: int = Field(
        default=2020,
        description="Religion census year (ARDA/ASARB)",
        ge=2000,
        le=2030,
    )

    acs_labels_year: int = Field(
        default=2020,
        description="ACS labels/metadata year",
        ge=2010,
        le=2030,
    )

    # =============================================================================
    # Database
    # =============================================================================
    database_url: str = Field(
        default="sqlite:///./cria.db",
        description="Database connection URL (SQLite default, PostgreSQL for production)",
    )

    test_database_url: Optional[str] = Field(
        default="sqlite:///./cria_test.db",
        description="Test database connection URL",
    )

    # =============================================================================
    # Paths (relative to project root)
    # =============================================================================
    data_dir: str = Field(
        default="data",
        description="Data directory",
    )

    output_dir: str = Field(
        default="data/output",
        description="Output directory (outputs are a type of data)",
    )

    logs_dir: str = Field(
        default="logs",
        description="Logs directory",
    )

    # =============================================================================
    # Processing Configuration
    # =============================================================================
    default_geography: str = Field(
        default="county",
        description="Default geography level",
        pattern="^(state|county|tract|tribal)$",
    )

    debug: bool = Field(
        default=True,
        description="Enable debug mode",
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )

    # =============================================================================
    # Pipeline Configuration
    # =============================================================================
    pipeline_timeout_minutes: int = Field(
        default=60,
        description="Maximum pipeline runtime in minutes before auto-termination",
        ge=5,
        le=1440,  # Max 24 hours
    )

    # =============================================================================
    # Testing
    # =============================================================================
    test_mode: bool = Field(
        default=False,
        description="Enable test mode (use smaller datasets)",
    )

    test_sample_size: int = Field(
        default=100,
        description="Sample size for testing",
        ge=10,
        le=10000,
    )

    # =============================================================================
    # Computed Properties
    # =============================================================================
    @property
    def years_dict(self) -> dict[str, int]:
        """Get all years as a dictionary (for backward compatibility)"""
        return {
            "acs": self.acs_year,
            "cbp": self.cbp_year,
            "naics": self.naics_year,
            "pop": self.pop_year,
            "asarb": self.asarb_year,
            "acs_labels": self.acs_labels_year,
        }

    @property
    def is_docker(self) -> bool:
        """Check if running in Docker (database host is 'postgres')"""
        return "postgres" in self.database_url.lower()


# Create global settings instance
# This will be imported throughout the application
settings = Settings()
