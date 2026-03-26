from flask import Flask, jsonify, request
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# GET /test
@app.get("/test")
def get_test():
    logging.info("GET /test")
    logging.info("HEADERS \n%s", request.headers)
    return jsonify({"message": "hello"}), 200


# POST /test
@app.post("/test")
def post_test():
    data = request.get_json(silent=True)  # body som JSON (eller None)
    logging.info("POST /test; data=%s", data)
    return jsonify({
        "message": "created",
        "data": data,
    }), 201


# PUT /test
@app.put("/test")
def put_test():
    data = request.get_json(silent=True)
    logging.info("PUT /test; data=%s", data)
    return jsonify({
        "message": "replaced",
        "data": data,
    }), 200


# PATCH /test
@app.patch("/test")
def patch_test():
    data = request.get_json(silent=True)
    logging.info("PATCH /test; data=%s", data)
    return jsonify({
        "message": "patched",
        "data": data,
    }), 200


# DELETE /test
@app.delete("/test")
def delete_test():
    logging.info("DELETE /test")
    # 204 = "No Content" (vanligt för DELETE)
    return "", 204


if __name__ == "__main__":
    app.run(port=3000, debug=True)
