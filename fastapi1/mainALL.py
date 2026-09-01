from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from databases import Database
from pydantic import BaseModel

# URL для PostgreSQL (ЗАМЕНИТЕ user, password, localhost, dbname на свои реальные данные!)
DATABASE_URL = "postgresql://myuser:123@localhost/mydatabase"

# Главный объект для работы с базой данных - используется во всех запросах
database = Database(DATABASE_URL)

# Базовый класс для моделей пользователя - содержит общие поля
class UserBase(BaseModel):
    username: str
    email: str

# Модель для получения данных от клиента (валидация ввода)
# Наследует все поля от UserBase и может быть расширена дополнительными полями
# Пример: на входе мы можем запросить пароль, который не будем возвращать в ответе
class UserCreate(UserBase):
    """
    Входная модель для создания пользователя. 
    В реальных проектах обычно содержит больше полей, чем выходная модель,
    например, пароль, подтверждение пароля или другие чувствительные данные.
    """
    pass  # В текущей реализации поля совпадают с базовой моделью

# Модель для возврата данных клиенту (сериализация вывода)
# Наследует общие поля и добавляет технические данные из БД
# Важно: выходная модель часто содержит меньше полей, чем входная
class UserReturn(UserBase):
    """
    Выходная модель пользователя. Демонстрирует:
    - Добавление служебных полей (id из БД)
    - Исключение чувствительных данных (если бы они были)
    - Формат данных, безопасный для возврата клиенту
    """
    id: int  # ID всегда присутствует после сохранения в БД

# Пример расширения моделей для учебных целей:
# class UserCreateWithPassword(UserCreate):
#     password: str
#     password_confirm: str

# class UserPrivateInfo(UserReturn):
#     created_at: datetime
#     last_login: datetime

# Управление подключением через lifespan (новый способ в FastAPI 0.95+)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Контекстный менеджер для управления подключением к БД.
    Заменяет устаревшие @app.on_event("startup") и @app.on_event("shutdown")
    """
    # Устанавливаем соединение при старте приложения
    await database.connect()
    yield  # Здесь работает приложение
    # Корректно закрываем подключение при завершении
    await database.disconnect()

app = FastAPI(lifespan=lifespan)

# Роут для создания пользователей с примерами валидации
@app.post("/users/", response_model=UserReturn)
async def create_user(user: UserCreate):
    """
    Создание пользователя с валидацией данных.
    
    Параметры:
    - user: данные согласно модели UserCreate
    
    Возвращает:
    - UserReturn с данными созданного пользователя и ID из БД
    
    Демонстрирует:
    - Разделение входных и выходных моделей
    - Автоматическую документацию в Swagger/OpenAPI
    - Обработку ошибок базы данных
    
    Пример использования транзакции:
    async with database.transaction():
        # несколько запросов в одной транзакции
        await database.execute(...)
        
    Дополнительно сам объект Database имеет свой асинхронный контекстный менеджер, то есть можно писать:
    async with Database(DATABASE_URL) as db:
    	await db.execute(...)
    
    Примеры выше полезны, если мы устанавливаем соединение не один раз при старте приложения, 
    а подключаемся к БД на каждый запрос (используем ресурсы по мере надобности, но чуть увеличиваем накладные расходы на создание соединения)
    """
    # SQL-запрос с параметризацией (защита от SQL-инъекций)
    query = """
        INSERT INTO users (username, email)
        VALUES (:username, :email)
        RETURNING id  /* Получаем автоматически сгенерированный ID */
    """
    
    try:
        # Пример использования транзакции (раскомментировать при необходимости):
        # async with database.transaction():
        user_id = await database.execute(
            query=query,
            values=user.model_dump()  # Автоматическая конвертация в словарь
        )
        
        # Комбинируем базовые поля с полученным ID
        return UserReturn(
            id=user_id,
            **user.model_dump(mode='json')  # Сериализация для ответа
        )
        
    except Exception as e:
        # В реальном проекте добавить логирование ошибки
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при создании пользователя: {str(e)}"
        )


# Эндпоинт для получения пользователя по ID
@app.get("/users/{user_id}", response_model=UserReturn)
async def get_user(user_id: int):
    """
    Получение информации о пользователе по его ID.
    
    Параметры:
    - user_id: идентификатор пользователя в БД
    
    Возвращает:
    - Данные пользователя в формате UserReturn
    - 404 ошибку если пользователь не найден
    """
    query = """
        SELECT id, username, email 
        FROM users 
        WHERE id = :user_id
    """
    try:
        result = await database.fetch_one(
            query=query,
            values={"user_id": user_id}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения пользователя: {str(e)}"
        )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Пользователь с указанным ID не найден"
        )

    return UserReturn(
        id=result["id"],
        username=result["username"],
        email=result["email"]
    )


# Роут для полного обновления информации о пользователе по ID
@app.put("/users/{user_id}", response_model=UserReturn)
async def update_user(user_id: int, user: UserCreate):
    """
    Полное обновление данных пользователя по ID (PUT-запрос).

    Параметры:
    - user_id: ID пользователя в базе данных
    - user: новые данные пользователя (все поля обязательны)

    Возвращает:
    - Обновленные данные пользователя в формате UserReturn
    - 404 ошибку если пользователь не найден
    - 500 ошибку при проблемах с базой данных

    Пример запроса:
    {
        "username": "new_username",
        "email": "new_email@example.com"
    }
    """
    # SQL-запрос с возвратом обновленных данных
    query = """
        UPDATE users
        SET username = :username, email = :email
        WHERE id = :user_id
        RETURNING id
    """

    values = {
        "user_id": user_id,
        "username": user.username,
        "email": user.email
    }

    try:
        # Выполняем запрос и получаем обновленные данные
        result = await database.execute(query=query, values=values)

        # Если запись не найдена
        if not result:
            raise HTTPException(
                status_code=404,
                detail="Пользователь с указанным ID не найден"
            )

        # Преобразуем результат запроса в модель UserReturn
        return UserReturn(**user.model_dump(), id=result,)

    except HTTPException as he:
        # Пробрасываем HTTPException из проверки выше
        raise he

    except Exception as e:
        # Обрабатываем другие ошибки базы данных
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обновления пользователя: {str(e)}"
        )
    

# Роут для удаления пользователя по ID
@app.delete("/users/{user_id}", response_model=dict)
async def delete_user(user_id: int):
    """
    Удаление пользователя из базы данных по ID.

    Параметры:
    - user_id: идентификатор пользователя для удаления

    Возвращает:
    - Сообщение об успешном удалении
    - 404 ошибку если пользователь не найден
    - 500 ошибку при проблемах с базой данных
    """
    query = """
        DELETE FROM users 
        WHERE id = :user_id
        RETURNING id
    """
    try:
        # Пытаемся удалить запись и получить подтверждение
        deleted_id = await database.execute(
            query=query,
            values={"user_id": user_id}
        )
        
        if not deleted_id:
            raise HTTPException(
                status_code=404,
                detail="Пользователь с указанным ID не найден"
            )
            
        return {"message": "Пользователь успешно удален"}
        
    except HTTPException as he:
        raise he
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка удаления пользователя: {str(e)}"
        )