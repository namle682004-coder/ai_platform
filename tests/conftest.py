import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Set required test environment variables before any module imports if not set by .env
os.environ.setdefault("TEST_MODE", "true")
os.environ.setdefault("VLLM_TEST_MODE", "true")
os.environ.setdefault("MASTER_PEPPER", "test-master-pepper-for-testing-purposes-min-32-chars")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-purposes-min-32-chars")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test_ai_platform")
os.environ.setdefault("MINIO_ROOT_PASSWORD", "minioadmin123")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
