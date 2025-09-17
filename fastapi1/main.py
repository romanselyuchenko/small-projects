from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from databases import Database
from pydantic import BaseModel

DATABASE_URL = "postgresql://myuser:123@localhost/mydatabase"

database = Database(DATABASE_URL)

class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    """"""

class UserReturn(UserBase):
    id: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    yield
    await database.disconnect()

app = FastAPI(lifespan=lifespan)

@app.post('/createuser', response_model=UserReturn)
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
        return UserReturn(id=user_id, **user.model_dump(mode='json'))
    except Exception as e:
        raise HTTPException(status_code=400)
    
@app.get('/users')
async def get_users():
    try:
        result = await database.fetch_all(
            """
            SELECT * FROM users;
        """
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=404)
    
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