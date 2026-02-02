from openai import OpenAI
import re

# Existing variables...
DOCTOR_CODES_RAW = ...

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY", "") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL", "") or "").strip() or "gpt-4.1-mini"

_oai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
