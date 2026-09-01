from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI()

sample_product_1 = {
    "product_id": 123,
    "name": "Smartphone",
    "category": "Electronics",
    "price": 599.99
}

sample_product_2 = {
    "product_id": 456,
    "name": "Phone Case",
    "category": "Accessories",
    "price": 19.99
}

sample_product_3 = {
    "product_id": 789,
    "name": "Iphone",
    "category": "Electronics",
    "price": 1299.99
}

sample_product_4 = {
    "product_id": 101,
    "name": "Headphones",
    "category": "Accessories",
    "price": 99.99
}

sample_product_5 = {
    "product_id": 202,
    "name": "Smartwatch",
    "category": "Electronics",
    "price": 299.99
}

sample_products = [sample_product_1, sample_product_2, sample_product_3, sample_product_4, sample_product_5]

class Product(BaseModel):
    product_id: int = Field(...,)
    name: str = Field(..., min_length=2, max_length=10)
    category: str = Field(min_length=2)
    price: float


@app.get('/product/{product_id}', response_model=Product)
async def get_product(product_id: int):
    for i in sample_products:
        if i["product_id"] == product_id:
            return i
    return {"error": "Product not found"}


@app.get('/products/search')
async def search(keyword: str, category: str = None, limit: int = 10) -> list[Product]:
    result_list = []
    for i in sample_products:
        if keyword.lower() in i['name'].lower() and category.lower() == i['category'].lower():
            result_list.append(i)
    return result_list[:limit]