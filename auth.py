import os
import time
import jwt
import bcrypt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = os.getenv("JWT_SECRET", "dev-only-secret-please-change-me-32chars!")
TOKEN_LIFETIME_SECONDS = 30 * 60  # 30 minutes

# One demo user. The password is hashed, never stored as plain text.
USERS = {
    "mercy": {
        "password_hash": bcrypt.hashpw(b"logistics2026", bcrypt.gensalt()),
        "role": "coordinator",
    },
    "james": {
        "password_hash": bcrypt.hashpw(b"newpassword", bcrypt.gensalt()),
        "role": "patient",
        }
}

def check_password(username: str, password: str) -> bool:
    user = USERS.get(username)
    if user is None:
        return False
    return bcrypt.checkpw(password.encode(), user["password_hash"])

def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "role": USERS[username]["role"],
        "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

bearer = HTTPBearer()

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired. Log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return payload

if __name__ == "__main__":
    print("Password correct:", check_password("mercy", "logistics2026"))
    print("Pssword wrong:", check_password("mercy", "wrongpassword"))
    token = create_token("mercy")
    print("JWT token:")
    print(token)

    print("Decode token:")
    print(jwt.decode(token, SECRET_KEY, algorithms=["HS256"])) 