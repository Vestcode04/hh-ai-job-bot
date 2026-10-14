import asyncio
import httpx
from os import getenv
from dotenv import load_dotenv

load_dotenv()


async def main():
    data = {
        "grant_type": "client_credentials",
        "client_id": getenv("HH_CLIENT_ID"),
        "client_secret": getenv("HH_CLIENT_SECRET")
    }

    headers = {
        "HH-User-Agent": getenv("HH_USER_AGENT")
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.hh.ru/token",
            data=data,
            headers=headers
        )

        response.raise_for_status()

        print("Access token:", response.json()["access_token"])


asyncio.run(main())