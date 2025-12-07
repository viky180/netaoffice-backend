# CivicStake Backend

FastAPI backend for the Civic Reputation Marketplace.

## Setup

```bash
# Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
copy .env.example .env
# Edit .env with your Supabase and Gemini credentials

# Run the server
uvicorn app.main:app --reload --port 8000
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
