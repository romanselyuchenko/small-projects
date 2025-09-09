from fastapi import FastAPI, Depends, status, HTTPException
from pydantic import BaseModel, Field
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext

app = FastAPI()
security = HTTPBasic()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserBase(BaseModel):
    username: str = Field(..., min_length=1, max_length=10) 

class User(UserBase):   # чтобы получять данные от пользователя
    password: str = Field(..., min_length=1, max_length=10)

class UserInDB(UserBase):     # чтобы внутри не было незашифрованных данных
    hashed_password: str = Field(...,)

# Симуляция базы данных в виде списка объектов пользователей
USER_DATA: list[UserInDB] = []


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_user_from_db(username: str) -> UserInDB | None:
    for user in USER_DATA:
        if user.username == username:
            return user
    return None

def authenticate_user(credentials: HTTPBasicCredentials = Depends(security)):   # выводит js окошко для ввода
    user = get_user_from_db(credentials.username)   # получаем из бд юзера с которым будем работать
    
    if user is None or not verify_password(credentials.password, user.hashed_password): #plain VS hash
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, 
                            detail="Invalid credentials", 
                            headers={"WWW-Authenticate": "Basic"})
    return user


@app.get("/login")
def login(user: User = Depends(authenticate_user)): # вся логика в функции

    return {"message": "You have access to the protected resource!", "user_info": user}

@app.post("/registration")
def user_registration(user: User):
    USER_DATA.append(UserInDB(username = user.username, hashed_password = get_password_hash(user.password)))
    return {"message": "You have accessfully registered!", "user_info": user}