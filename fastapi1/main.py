from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from contextlib import asynccontextmanager
from databases import Database
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import Optional

DATABASE_URL = "postgresql://myuser:123@localhost/mydatabase" #todo_tasks #myusers
TOTAL = 10
forbiden_words = ['popa']

database = Database(DATABASE_URL)

class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    """"""

class UserReturn(UserBase):
    id: int
    created_at: datetime

class ToDoTask(BaseModel):
    # id: int (primal key in DB)
    title: str = Field(...,)
    description: str = Field(...,)
    complition: bool = False
    created_at: Optional[datetime]  # бд проставляет время
    # updated_at: Optional[datetime]

class UpdTask(ToDoTask):
    id: int

class ItemsResponse(BaseModel):
    item_id: int
    

# ДОБАВИЛИ модель пидантика для ошибок  
class CustomExceptionModel(BaseModel):
    status_code: int
    er_details: str 
    er_message: str

# ДОБАВИЛИ кастомное поле в модель кастомной ошибки
class CustomExceptionTOTAL(HTTPException):
    def __init__(self, detail: str, status_code: int, message: str):
        super().__init__(status_code=status_code, detail=detail)
        self.message = message

class CustomExceptionForbidenWords(HTTPException):
    def __init__(self, detail: str):
        status_code = 400
        message = "Your input contains forbidden words."
        super().__init__(status_code=status_code, detail=detail)
        self.message = message


@asynccontextmanager  # это вообще зачем
async def lifespan(app: FastAPI):
    await database.connect()
    yield
    await database.disconnect()

app = FastAPI(lifespan=lifespan)

@app.exception_handler(CustomExceptionTOTAL)
async def custom_exception_handler(request: Request, exc: CustomExceptionTOTAL) -> JSONResponse:
    error = jsonable_encoder(CustomExceptionModel(status_code=exc.status_code, er_details=exc.detail, er_message=exc.message))
    return JSONResponse(status_code=exc.status_code, content=error)

@app.exception_handler(CustomExceptionForbidenWords)
async def custom_exception_handler(request: Request, exc: CustomExceptionForbidenWords) -> JSONResponse:
    error = jsonable_encoder(CustomExceptionModel(status_code=exc.status_code, er_details=exc.detail, er_message=exc.message))
    return JSONResponse(status_code=exc.status_code, content=error)

@app.get('/task/{id}')
async def get_task_by_id(id: int):
    try:
        if id > TOTAL:
            raise CustomExceptionTOTAL(detail="This item cannot exist.", status_code=404, message=f"Only {TOTAL} items are available.")
        query = "SELECT * FROM todo_tasks WHERE id=:id"
        values = {'id': id}
        result = await database.fetch_all(query=query, values=values)
        return result
    except CustomExceptionTOTAL:
        raise  # пробрасываем дальше, чтобы сработал handler

    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post('/create_user')
# @app.post('/createuser', response_model=UserReturn)
async def create_user(user: UserCreate):
    query = '''
    INSERT INTO users (username, email)
    VALUES (:username, :email)
    RETURNING id
    '''
    try:
        user_id = await database.execute(
            query=query,
            values=user.model_dump()
        )
        # return UserReturn(id=user_id, **user.model_dump(mode='json'))
        return user_id
    except Exception as e:
        raise HTTPException(status_code=400)
    
@app.get('/users')
async def get_users(by_name: str, limit: int = 10, offset: int = 0, sort_by: str | None = None):
    try:
        result = await database.fetch_all(
            """
            SELECT * FROM users;
        """
        )

        if sort_by == 'created_at':
            result = sorted(result, key=lambda x: x['created_at'])
        elif sort_by == '-created_at':
            result = sorted(result, key=lambda x: x['created_at'], reverse=True)
        else:
            raise HTTPException(status_code=400, detail='Unacceptable sort_by parameter.')


        if offset < limit:
            return result[offset:(offset + limit)]
        else:
            raise HTTPException(status_code=400, detail='Wrong query parameters.')
        

    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    
@app.put('/change_user', response_model=UserReturn)
async def change_user(user: UserReturn):
    query = """
        UPDATE users
        SET username = :username, email = :email
        WHERE id = :user_id
        RETURNING id
    """
    values = {
        'username': user.username,
        'email': user.email,
        'user_id': user.id
    }
    try:
        result = await database.execute(
            query=query, values=values
        )
        return UserReturn(**values, id=result)
    except Exception as e:
        raise HTTPException(status_code=404)
    
@app.delete('/delete_user')
async def delete_user(user_id: int):
    query = """
        DELETE FROM users 
        WHERE id = :user_id
        RETURNING id
    """
    values = {
        'user_id': user_id
    }
    try:
        result = await database.execute(
            query=query, values=values
        )
        if not result:
            raise HTTPException(status_code=500, detail='User is not found.')
        return f'User with ID {result} is deleted.'
    except Exception as e:
        raise HTTPException(status_code=404)
    
@app.post('/add_task')
# @app.post('/createuser', response_model=UserReturn)
async def add_task(task: ToDoTask):

    query = '''
    INSERT INTO todo_tasks (title, description, complition)
    VALUES (:title, :description, :complition)
    RETURNING id
    '''
    values = {
    "title": task.title,
    "description": task.description,
    "complition": task.complition
    }
    
    try:
        for word in forbiden_words:
            if word in task.title.lower() or word in task.description.lower():
                raise CustomExceptionForbidenWords(detail='/add_task')
        task_id = await database.execute(
            query=query,
            values=values
        )
        # return UserReturn(id=user_id, **user.model_dump(mode='json'))
        return task_id
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@app.get('/tasks')
async def get_tasks(complition: Optional[bool] = None,
                    created_after: Optional[datetime] = None,
                    created_before: Optional[datetime] = None,
                    title_contains: Optional[str] = None,
                    limit: int = 10,
                    offset: int = 0, 
                    sort_by: str = 'created_at'
                ):
    try:
        query = "SELECT * FROM todo_tasks WHERE TRUE"
        values = {}

        # фильтры
        if created_after:
            query += " AND created_at >= :created_after"
            values["created_after"] = created_after

        if created_before:
            query += " AND created_at <= :created_before"
            values["created_before"] = created_before

        if complition is not None:
            query += " AND complition = :complition"
            values["complition"] = complition
        
        if title_contains:
            query += " AND title ILIKE :title_contains"
            values['title_contains'] = f'%{title_contains}%'

        # сортировка
        if sort_by in {"created_at", "complited_at"}:
            query += f" ORDER BY {sort_by} ASC"
        elif sort_by in {"-created_at", "-complited_at"}:
            query += f" ORDER BY {sort_by[1:]} DESC"
        else:
            query += " ORDER BY id ASC"  # дефолт

        # пагинация
        query += " LIMIT :limit OFFSET :offset"
        values["limit"] = limit
        values["offset"] = offset    
        
        result = await database.fetch_all(query=query, values=values)
        return result
        # if sort_by == 'created_at':
        #     result = sorted(result, key=lambda x: x['created_at'])
        # elif sort_by == '-created_at':
        #     result = sorted(result, key=lambda x: x['created_at'], reverse=True)
        # else:
        #     raise HTTPException(status_code=400, detail='Unacceptable sort_by parameter.')


        # if offset < limit:
        #     return result[offset:(offset + limit)]
        # else:
        #     raise HTTPException(status_code=400, detail='Wrong query parameters.')
        

    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    

@app.put('/update_task', response_model=UpdTask)
async def update_task(id: int, title: Optional[str] = None, description: Optional[str] = None, complition: Optional[bool] = None):

    values = {"id": id}
    set_clauses = []

    if title is not None:
        set_clauses.append("title = :title")
        values["title"] = title

    if description is not None:
        set_clauses.append("description = :description")
        values["description"] = description

    if complition is not None:
        set_clauses.append("complition = :complition")
        values["complition"] = complition

    if not set_clauses:
        raise HTTPException(status_code=400, detail="Нечего обновлять")

    query = f"""
        UPDATE todo_tasks
        SET {', '.join(set_clauses)}
        WHERE id = :id
        RETURNING id, title, description, complition, created_at, complited_at
    """

    try:
        row = await database.fetch_one(query=query, values=values)
        if not row:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        return UpdTask(**dict(row))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.get('/tasks/statistics')
async def statistics():
    try:
        query = "SELECT * FROM todo_tasks"
        values = {}
   

        result = await database.fetch_all(query=query, values=values)
        complited_tasks = [i for i in result if i['complition'] == True]
        not_complited_tasks = [i for i in result if i['complition'] == False]

        total_complition_time = sum([i['complited_at'] - i['created_at'] for i in complited_tasks if i["complited_at"]], timedelta(0))

        avg_time = (
            total_complition_time / len(complited_tasks)
            if complited_tasks else None
        )


        return {'Общее количество задач: ': len(result),
                'Завершенных задач: ': {'true': len(complited_tasks), 'false': len(not_complited_tasks)},
                'Среднее время завершения задачи: ': int(avg_time.total_seconds() / 3600)
                }

    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))