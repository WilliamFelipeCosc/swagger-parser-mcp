from fastapi import FastAPI
from internal.main import main

app = FastAPI()

@app.get("/")
async def root():
    enums = main()
    return {"message": "Hello World", "enums": enums}