from services.mcp import combined_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(combined_app, host="localhost", port=9876)