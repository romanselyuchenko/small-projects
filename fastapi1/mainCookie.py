from fastapi import FastAPI, Response, Cookie
from pydantic import BaseModel, Field
import uuid
from itsdangerous import URLSafeSerializer
from datetime import datetime, timedelta

app = FastAPI()
SECRET_KEY = "super-secret-key"
serializer = URLSafeSerializer(SECRET_KEY)

# { session_id: user_login }
sessions = {}
sessions_expiry = {}

registered_users = [
    {'login': 'Vasia', 'password': '12345'},
    {'login': 'Petia', 'password': 'qwerty'}
]

class Login(BaseModel):
    login: str = Field(..., min_length=2, max_length=10)
    password: str = Field(..., min_length=2, max_length=10)


def create_session(user_login: str) -> str:

    session_id = str(uuid.uuid4())  # случайный UUID
    sessions[session_id] = user_login # запись в список сессий

    # установка времени жизни токена
    expiry = datetime.now() + timedelta(minutes=5)
    sessions_expiry[session_id] = expiry # запись в наш словарь сессий
    return session_id


def check_session(session_id: str | None) -> bool:
    if not session_id:              # проверяем если куки вообще
        return "Unauthorized (no cookie found)"
    try:
        uuid.UUID(session_id)       # проверка формата
    except ValueError:
        return "Unauthorized (invalid UUID)"
    
    user_login = sessions.get(session_id) # смотрим в наше словаре
    if user_login:
        return True
    else:
        return False


@app.post('/login')
async def login(login_data: Login, response: Response):  # описываем что мы принимаем и отдаем
    for user in registered_users:
        if login_data.login == user['login'] and login_data.password == user['password']:
            
            session_id = create_session(user['login'])

            # формируем значение cookie (<session_id>.<signature>)
            token = serializer.dumps(session_id)
            response.set_cookie(key="session_token", value=token, max_age=300, httponly=True)
            return {"Success": f"Welcome {user['login']}!"}
    return {"error": "User not found."}


@app.get('/profile')
async def get_user(response: Response, session_token: str | None = Cookie(default=None)):

    try:
        # достаём session_id и проверяем подпись
        session_id = serializer.loads(session_token)
    except Exception:
        return {"error": "Invalid or tampered session token"}
    
    now = datetime.now()
    remaining = sessions_expiry[session_id] - now # сколько осталось

    if remaining <= timedelta(minutes=3):

        # (обновляем) Создаем новую куку
        user_login = sessions.get(session_id)
        session_id = create_session(user_login) # Перезаписываем сессию

        token = serializer.dumps(session_id)
        response.set_cookie(key="session_token", value=token, max_age=300, httponly=True)

        return {"message": check_session(session_id)}
    else:
        return {"message": 'session expired'}