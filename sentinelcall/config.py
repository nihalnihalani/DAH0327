"""Centralized configuration for SentinelCall. All modules import from here."""
import os
from dotenv import load_dotenv

load_dotenv()

# Auth0
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "")
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID", "")
AUTH0_CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET", "")
AUTH0_SECRET = os.getenv("AUTH0_SECRET", "")

# Bland AI
BLAND_API_KEY = os.getenv("BLAND_API_KEY", "")

# Ghost CMS
GHOST_URL = os.getenv("GHOST_URL", "")
GHOST_ADMIN_API_KEY = os.getenv("GHOST_ADMIN_API_KEY", "")

# TrueFoundry
TRUEFOUNDRY_API_KEY = os.getenv("TRUEFOUNDRY_API_KEY", "")
TRUEFOUNDRY_ENDPOINT = os.getenv("TRUEFOUNDRY_ENDPOINT", "")

# Overmind
OVERMIND_API_KEY = os.getenv("OVERMIND_API_KEY", "")

# Airbyte
AIRBYTE_API_KEY = os.getenv("AIRBYTE_API_KEY", "")

# LLM Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# On-call
ON_CALL_PHONE = os.getenv("ON_CALL_PHONE", "+1234567890")
ON_CALL_ENGINEER_ID = os.getenv("ON_CALL_ENGINEER_ID", "engineer-001")

# GitHub
GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Webhook
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")
