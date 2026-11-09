import asyncio
from common.repositories.endpoint_repository import endpoint_repository

async def main():
    eps = await endpoint_repository.list_endpoints()
    print("Total:", len(eps))
    for k, v in list(eps.items())[:5]:
        print(f"Key: {k} | Name: {v.get('name')} | Path: {v.get('path')} | Quota: {v.get('free_quota')}")

if __name__ == "__main__":
    asyncio.run(main())

