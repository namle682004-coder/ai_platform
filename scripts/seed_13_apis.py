import asyncio

from src.admin.endpoint_catalog import seed_endpoint_catalog


if __name__ == "__main__":
    asyncio.run(seed_endpoint_catalog())
