import asyncio
from common.repositories.endpoint_repository import endpoint_repository
async def check():
    eps = await endpoint_repository.list_endpoints()
    for e in eps: print(e.get('name'))
if __name__ == '__main__':
    asyncio.run(check())
