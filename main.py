from dotenv.main import load_dotenv
from src.bot import init_bot


if __name__ == "__main__":
    load_dotenv()
    init_bot()
