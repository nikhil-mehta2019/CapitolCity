from jose import jwt
from datetime import datetime, timedelta, timezone

secret = "8f4b2c91e71a4f98b52d7c3e9f8a1d6c4e2b7a9f4c6d8e1f9a2b3c4d5e6f7a8"

expire_time = datetime.now(timezone.utc) + timedelta(hours=2)

payload = {
    "sub": "test@email.com",
    "role": "sales_rep",
    "exp": int(expire_time.timestamp())
}

token = jwt.encode(payload, secret, algorithm="HS256")

print(token)