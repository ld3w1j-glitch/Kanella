import os
from waitress import serve
from app import create_app

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5057"))
    # Railway termina HTTPS no proxy. O Waitress descarta cabeçalhos não
    # confiáveis por padrão, então define-se o esquema no ambiente de produção.
    options = {"url_scheme": "https"} if os.getenv("APP_ENV") == "production" else {}
    print(f"Kanella Barber Shop: http://{host}:{port}", flush=True)
    serve(create_app(), host=host, port=port, threads=6, **options)
