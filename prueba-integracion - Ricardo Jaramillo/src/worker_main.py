import asyncio

from app.queue.worker import start_worker


if __name__ == "__main__":
    asyncio.run(start_worker())