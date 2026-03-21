"""
EnvValidator — validates required environment variables before startup.
Prevents silent failures from missing API keys.
Prints clear error messages for missing/invalid vars.
"""
import os
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EnvVar:
    name: str
    required: bool = True
    description: str = ""
    example: str = ""
    min_length: int = 8
    can_be_empty: bool = False


# ── Required environment variables ────────────────────────────
REQUIRED_VARS = [
    EnvVar("GROQ_API_KEY", required=True,
           description="Groq API key — primary LLM router",
           example="gsk_..."),
    EnvVar("GEMINI_API_KEY", required=True,
           description="Google Gemini API key — fallback LLM",
           example="AIzaSy..."),
    EnvVar("OPENROUTER_API_KEY", required=True,
           description="OpenRouter API key — tertiary LLM",
           example="sk-or-..."),
    EnvVar("TELEGRAM_BOT_TOKEN", required=True,
           description="Telegram bot token for notifications",
           example="123456:ABC..."),
    EnvVar("GITHUB_TOKEN", required=True,
           description="GitHub personal access token",
           example="ghp_..."),
]

# ── Optional environment variables ────────────────────────────
OPTIONAL_VARS = [
    EnvVar("FOOTBALL_DATA_API_KEY", required=False,
           description="football-data.org API key for sports analytics",
           example="abc123..."),
    EnvVar("GMAIL_CLIENT_ID", required=False,
           description="Gmail OAuth client ID"),
    EnvVar("GMAIL_CLIENT_SECRET", required=False,
           description="Gmail OAuth client secret"),
    EnvVar("OPENCODE_API_BASE", required=False,
           description="OpenCode API base URL"),
    EnvVar("SUPABASE_URL", required=False,
           description="Supabase project URL"),
    EnvVar("SUPABASE_KEY", required=False,
           description="Supabase anon/service key"),
]


class EnvValidator:
    """Validate environment before startup."""

    def __init__(self, strict: bool = True):
        self.strict = strict  # if True, raise on missing required vars
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate all required env vars.
        Returns (is_valid: bool, errors: list[str]).
        """
        errors = []
        warnings = []

        for var in REQUIRED_VARS:
            value = os.environ.get(var.name, "")
            if not value or (not var.can_be_empty and len(value.strip()) < var.min_length):
                errors.append(
                    f"MISSING: {var.name} — {var.description}\n"
                    f"         Example: {var.name}={var.example}"
                )

        for var in OPTIONAL_VARS:
            value = os.environ.get(var.name, "")
            if not value:
                warnings.append(f"OPTIONAL (not set): {var.name} — {var.description}")

        if warnings:
            for w in warnings:
                self.logger.debug(w)

        is_valid = len(errors) == 0
        return is_valid, errors

    def validate_or_exit(self) -> None:
        """Validate env vars — exit with code 1 if any required var is missing."""
        is_valid, errors = self.validate()
        if not is_valid:
            print("\n❌ The Moon — Environment validation FAILED\n")
            for err in errors:
                print(f"  {err}")
            print(
                "\nSet missing variables in your .env file or environment.\n"
                "Reference: .env.example\n"
            )
            raise SystemExit(1)
        self.logger.info(
            f"Environment validated ✅ "
            f"({len(REQUIRED_VARS)} required vars OK)"
        )

    def get_status(self) -> dict:
        """Return env validation status without raising."""
        is_valid, errors = self.validate()
        optional_set = [
            v.name for v in OPTIONAL_VARS
            if os.environ.get(v.name, "")
        ]
        return {
            "valid": is_valid,
            "errors": errors,
            "required_count": len(REQUIRED_VARS),
            "optional_set": optional_set,
            "optional_count": len(optional_set),
        }