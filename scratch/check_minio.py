import asyncio
from minio import Minio

def check_minio():
    client = Minio(
        "172.16.20.2:9000",
        access_key="minioadmin",
        secret_key="minioadmin123",
        secure=False
    )
    buckets = client.list_buckets()
    print("Buckets:", [b.name for b in buckets])
    
    objects = list(client.list_objects("aip-data", prefix="", recursive=True))
    print(f"Total objects in aip-data: {len(objects)}")
    for obj in objects:
        if "310" in obj.object_name or "họp" in obj.object_name:
            print("Found in MinIO:", obj.object_name, obj.size)

if __name__ == "__main__":
    check_minio()

