import uvicorn

from .config import load_settings


def main():
    settings = load_settings()
    uvicorn.run(
        "chainguard_gateway.main:app", host=settings.host, port=settings.port,
        log_level=settings.log_level, timeout_graceful_shutdown=settings.shutdown_timeout,
        server_header=False,
    )


if __name__ == "__main__":
    main()
