# Start from a small official Python image
FROM python:3.12-slim

# Work inside /app in the image
WORKDIR /app

# Install dependencies first, so this layer is cached
# and rebuilds are fast when only code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy our code
COPY auth.py triage_model_call.py ./

# The service listens on port 8000
EXPOSE 8000

# What runs when the container starts
CMD ["uvicorn", "triage_model_call:app", "--host", "0.0.0.0", "--port", "8000"]