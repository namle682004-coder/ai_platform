#!/usr/bin/env bash
ssh msp "docker inspect aip-rag-api" | grep -iE 'mongo|qdrant|redis|rabbit' | head -n 30

