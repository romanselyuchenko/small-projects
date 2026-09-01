from fastapi import FastAPI, Depends
from pydantic import BaseModel, Field
from database import get_db_connection
import asyncpg

app = FastAPI()

class User(BaseModel):
    username: str = Field(..., min_length=2, max_length=20)
    password: str = Field(..., min_length=2, max_length=20)

class ToDo(BaseModel):
    id: int = Field()
    title: str = Field(..., min_length=2, max_length=10)
    description: str = Field()
    complition: bool = False
    user_id: int = Field()

@app.post("/add_task")
async def add_task(task: ToDo, db: asyncpg.Connection = Depends(get_db_connection)):
    row = await db.fetchrow(
        """
        INSERT INTO todolist (title, description, complition, user_id)
        VALUES ($1, $2, $3, $4)
        RETURNING id, title, description, complition, user_id
        """,
        task.title,
        task.description,
        task.complition,
        task.user_id
    )
    return dict(row)

@app.get("/tasks_list")
async def get_tasks_list(db: asyncpg.Connection = Depends(get_db_connection)):
    rows = await db.fetch("SELECT * FROM todolist")
    return rows

@app.post("/update_task")
async def update_task_task(task: ToDo, db: asyncpg.Connection = Depends(get_db_connection)):
    row = await db.fetchrow(
    "UPDATE todolist SET title=$1, description=$2, complition=$3, user_id=$4 WHERE id=$5 RETURNING *",
    task.title,
    task.description,
    task.complition,
    task.user_id,
    task.id
    )
    return dict(row)

@app.delete("/delete_task")
async def delete_task(task_id: int, db: asyncpg.Connection = Depends(get_db_connection)):
    row = await db.fetchrow(
        """
        DELETE FROM todolist
        WHERE id=$1
        RETURNING *
        """,
        task_id
    )
    if row is None:
        return {"error": "Task not found"}
    return {"message": f"Task {task_id} deleted", "task": dict(row)}

@app.delete("/delete_user")
async def delete_user(user_id: int, db: asyncpg.Connection = Depends(get_db_connection)):
    row = await db.fetchrow(
        """
        DELETE FROM users
        WHERE id=$1
        RETURNING *
        """,
        user_id
    )
    if row is None:
        return {"error": "User not found"}
    return {"message": f"User {user_id} deleted", "data": dict(row)}