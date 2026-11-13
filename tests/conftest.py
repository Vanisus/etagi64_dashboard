import os

os.environ.setdefault("POSTGRES_USER", "etagi")
os.environ.setdefault("POSTGRES_PASSWORD", "test-password")
os.environ.setdefault("POSTGRES_DB", "etagi_test")
os.environ.setdefault("AUTH_ALLOWED_ORIGINS", "http://localhost:5173")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")
