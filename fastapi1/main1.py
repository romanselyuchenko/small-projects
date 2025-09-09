from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI()

# fake_db = [
#     {"user_name": "vasya", "user_info": "любит колбасу"},
#     {"user_name": "katya", "user_info": "любит петь"}
# ]

# unacceptable_words = ['бяк', 'козявк', 'редиск']

# feedbacks = []

# class User(BaseModel):
#     user_name : str
#     user_info : str


class Feedback(BaseModel):
    user_name: str = Field(..., min_length=2, max_length=50)
    message: str = Field(..., min_length=10, max_length=500)


# class Contact(BaseModel):
#     email: str = Field(..., pattern=r"[^@]+@[^@]+\.[^@]+", description="Электронная почта должна быть в корректном формате")
#     phone_number: str = Field(pattern=r"^\+\d{1,3}\s?\d{4,14}$", description="Номер телефона должен быть в формате +123456789")


# @app.get("/user/{user_name}")
# async def user(user_name: str):
#     result = [el for el in fake_db if el['user_name'] == user_name]
#     return result[0] if result else None

# @app.get("/users")
# async def users(limit: int = 10, vasia: str = 'Vasia?'):
#     return fake_db[:limit]

# @app.post("/add_user")
# async def add_user(user: User):
#     fake_db.append({"user_name": user.user_name, "user_info": user.user_info})
#     result = [el for el in fake_db if el['user_name'] == user.user_name]
#     return fake_db

# @app.post("/feedback")
# async def feedback(feedback: Feedback, contact: Contact, is_premium: bool = False):
#     flag = True
#     for word in unacceptable_words:
#         if word.lower() in feedback.message.lower():
#             flag = False

#     if flag and is_premium:
#         feedbacks.append(feedback.message)
#         return {
#         "message": f"Спасибо, {feedback.user_name}! Ваш отзыв сохранён. Ваш отзыв будет рассмотрен в приоритетном порядке."
#         }
#     elif flag:
#         feedbacks.append(feedback.message)
#         return {
#         "message": f"Feedback received. Thank you, {feedback.user_name}."
#         }
#     else:
#         return {'ValueError': "Использование недопустимых слов"}

class UserCreate(BaseModel):
     desc: str | None = None
                   # или

     name: str = Field(..., min_length=2, max_length=10)
     email: str = Field(..., pattern=r"[^@]+@[^@]+\.[^@]+", description="Электронная почта должна быть в корректном формате")
     age: int = Field(ge=1)
     is_subscribed: bool = False


@app.post('/create_user')
async def create_user(user: UserCreate):
    return user