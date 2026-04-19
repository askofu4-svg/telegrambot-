import config
import bot


def main() -> None:
    config.validate_environment()
    print("🤖 Bot is starting...")

    try:
        bot.main()
    except KeyboardInterrupt:
        print("✅ Bot has stopped")


if __name__ == "__main__":
    main()
