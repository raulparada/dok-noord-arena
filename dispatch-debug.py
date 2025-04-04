"""
Used for Github Actions `workflow_dispatch`es local debugging.
"""

from flask import Flask, Request, request

app = Flask(__name__)


class CorsMiddleware:
    """
    Minimal, allow-all CORS middleware.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        def cors_response(status: str, response_headers: list, exc_info=None):
            response_headers.append(("Access-Control-Allow-Origin", "*"))
            if Request(environ).method == "OPTIONS":
                response_headers.append(("Access-Control-Allow-Headers", "*"))
                response_headers.append(("Access-Control-Allow-Methods", "*"))
            return start_response(status, response_headers, exc_info)

        return self.app(environ, cors_response)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def debug(path: str):
    print("Path:", path)
    print(f"Headers: {request.headers}")
    print(f"Body: {request.get_data(as_text=True)}")
    return "Request logged", 200


if __name__ == "__main__":
    app.wsgi_app = CorsMiddleware(app.wsgi_app)
    app.run(port=7654, debug=True)
