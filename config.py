import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PREMIUM_CHANNEL_INVITE = os.getenv("PREMIUM_CHANNEL_INVITE")
HASHBACK_MERCHANT_CODE = os.getenv("HASHBACK_MERCHANT_CODE")
HASHBACK_CALLBACK_URL = os.getenv("HASHBACK_CALLBACK_URL")
HASHBACK_API_URL = os.getenv("HASHBACK_API_URL")
HASHBACK_API_KEY = os.getenv("HASHBACK_API_KEY")
PREMIUM_AMOUNT = int(os.getenv("PREMIUM_AMOUNT", "300"))

REQUIRED_ENV = [
    "BOT_TOKEN",
    "PREMIUM_CHANNEL_INVITE",
    "HASHBACK_MERCHANT_CODE",
    "HASHBACK_CALLBACK_URL",
    "HASHBACK_API_URL",
    "HASHBACK_API_KEY",
]


def validate_environment() -> None:
    missing = [name for name in REQUIRED_ENV if not globals().get(name)]
    if missing:
        raise EnvironmentError(
            "Missing required environment variables: {}".format(
                ", ".join(missing)
            )
        )
