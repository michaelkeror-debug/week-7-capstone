# triage_api.py

from auth import check_password, create_token, current_user

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field, ConfigDict



# FastAPI application
app = FastAPI(
    title="AfyaPlus Triage API",
    version="1.0.0"
)



# Login model
class LoginRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=50
    )

    password: str = Field(
        ...,
        min_length=8,
        max_length=128
    )


# Request model
class TriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_message: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Patient's symptoms or medical message"
    )

    county: str = Field(
        ...,
        min_length=2,
        max_length=40,
        description="Patient's county"
    )



# Response model
class TriageResponse(BaseModel):
    urgency: str = Field(
        ...,
        pattern="^(low|medium|high)$"
    )

    advice: str = Field(
        ...,
        min_length=5,
        max_length=1000
    )

    model_used: str = Field(
        ...,
        min_length=1,
        max_length=100
    )

    handled_for: str = Field(
        ...,
        min_length=1,
        max_length=100
    )



# AI MODEL
URGENT_WORDS = [
    "chest pain",
    "bleeding",
    "unconscious",
    "cannot breathe",
    "difficulty breathing"
]


def triage_model(message: str) -> dict:

    text = message.lower()

    if any(word in text for word in URGENT_WORDS):
        return {
            "urgency": "high",
            "advice": (
                "Please seek emergency medical care immediately "
                "at the nearest appropriate facility."
            )
        }

    return {
        "urgency": "low",
        "advice": (
            "Rest, drink fluids, and monitor your symptoms. "
            "Seek medical care if symptoms worsen."
        )
    }


def require_coordinator(user: dict = Depends(current_user)):

    if user.get("role") != "coordinator":
        raise HTTPException(
            status_code=403,
            detail="Coordinator role required"
        )

    return user






# Health check
@app.get("/health")
def health():

    return {
        "service": "triage-api",
        "version": "1.0.0",
        "status": "healthy"
    }



# Login
@app.post("/token")
def login(body: LoginRequest):

    if not check_password(body.username, body.password):
        raise HTTPException(
            status_code=401,
            detail="Wrong username or password."
        )

    return {
        "access_token": create_token(body.username),
        "token_type": "bearer"
    }



# Protected triage endpoint
@app.post(
    "/triage",
    response_model=TriageResponse
)
def triage(
    request: TriageRequest,
    user: dict = Depends(require_coordinator)
):

    try:
        result = triage_model(request.patient_message)

        return TriageResponse(
            urgency=result["urgency"],
            advice=result["advice"],
            model_used="triage-stub-v1",
            handled_for=user["sub"]
        )

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="The AI model is temporarily unavailable."
        )