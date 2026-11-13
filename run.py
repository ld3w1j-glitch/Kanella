import os
from waitress import serve
from app import create_app

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5057"))
    print(f"Kanella Barber Shop: http://{host}:{port}", flush=True)
    serve(create_app(), host=host, port=port, threads=6)
