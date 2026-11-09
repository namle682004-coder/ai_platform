#!/usr/bin/env bash
ssh msp 'docker exec aip-rag-api python3 -c "
from minio import Minio
client = Minio(\"aip-minio:9000\", access_key=\"minioadmin\", secret_key=\"minioadmin\", secure=False)
for o in client.list_objects(\"aip-data\", recursive=True):
    if \"2db8d7b271e2\" in o.object_name:
        print(\"Found doc_2db8d7b271e2:\", o.object_name, o.size)
"'
