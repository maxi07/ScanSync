"""Strict HTTP simulator for Microsoft device auth, Graph and OpenAI."""

import io
import re
import threading
import uuid

from flask import Flask, Response, jsonify, request, send_file


app = Flask(__name__)
lock = threading.Lock()
state = {"authorized": False, "openai_error": False, "upload_error": False, "calls": [], "uploads": []}
payloads = {}


@app.after_request
def record(response):
    if request.path.startswith(("/identity/", "/graph/", "/openai/")):
        with lock:
            state["calls"].append({"method": request.method, "path": request.path, "status": response.status_code})
    return response


@app.get('/health')
def health():
    return jsonify(ok=True)


@app.route('/control', methods=['GET', 'POST'])
def control():
    with lock:
        if request.method == 'POST':
            changes = request.get_json()
            if set(changes) - {"openai_error", "upload_error", "clear"}:
                return jsonify(error="Unknown control"), 400
            for name in ("openai_error", "upload_error"):
                if name in changes:
                    state[name] = bool(changes[name])
            if changes.get("clear"):
                state["calls"].clear()
                state["uploads"].clear()
                payloads.clear()
        return jsonify(state)


@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'POST':
        if request.form.get('code') != 'E2E-CODE':
            return 'Invalid device code', 400
        state['authorized'] = True
        return '<h1>Signed in as ScanSync E2E</h1>'
    return '''<!doctype html><title>Microsoft Test Sign-In</title>
        <h1>Microsoft Test Sign-In</h1><form method="post">
        <label for="code">Device code</label><input id="code" name="code" required>
        <button type="submit">Authorize ScanSync</button></form>'''


@app.route('/identity/<path:path>', methods=['GET', 'POST'])
def identity(path):
    authority = 'https://login.microsoftonline.com/consumers'
    if path.endswith('/discovery/instance'):
        return jsonify(
            tenant_discovery_endpoint=f'{authority}/v2.0/.well-known/openid-configuration',
            metadata=[{"preferred_network": "login.microsoftonline.com", "preferred_cache": "login.microsoftonline.com",
                       "aliases": ["login.microsoftonline.com"]}],
        )
    if path.endswith('/.well-known/openid-configuration'):
        return jsonify(
            issuer=f'{authority}/v2.0',
            authorization_endpoint=f'{authority}/oauth2/v2.0/authorize',
            token_endpoint=f'{authority}/oauth2/v2.0/token',
            device_authorization_endpoint=f'{authority}/oauth2/v2.0/devicecode',
            jwks_uri=f'{authority}/discovery/v2.0/keys',
        )
    if path.endswith('/devicecode') and request.method == 'POST':
        return jsonify(device_code='e2e-device', user_code='E2E-CODE', expires_in=900, interval=1,
                       verification_uri='http://mock-api:8080/verify', message='Enter E2E-CODE')
    if path.endswith('/token') and request.method == 'POST':
        if not state['authorized']:
            return jsonify(error='authorization_pending', error_description='Waiting for browser consent'), 400
        return jsonify(access_token='e2e-access-token', refresh_token='e2e-refresh-token', expires_in=86400,
                       token_type='Bearer', scope='Files.ReadWrite.All User.Read')
    return jsonify(error=f'Unexpected identity request: {path}'), 501


@app.route('/graph/<path:path>', methods=['GET', 'PUT'])
def graph(path):
    if request.headers.get('Authorization') != 'Bearer e2e-access-token':
        return jsonify(error='Missing test access token'), 401
    if request.method == 'GET':
        if path == 'v1.0/me':
            return jsonify(id='e2e-user', displayName='ScanSync E2E', mail='e2e@example.test')
        if path == 'v1.0/me/photo/$value':
            return Response(status=404)
        if path.rstrip('/') == 'v1.0/me/drive/root':
            return jsonify(id='root')
        if path == 'v1.0/me/drive/sharedWithMe':
            return jsonify(value=[])
        if path == 'v1.0/me/drive/items/root/children':
            return jsonify(value=[
                {"id": f"folder-{suffix}", "name": name, "folder": {"childCount": 0},
                 "webUrl": f"https://onedrive.example.test/{name}",
                 "parentReference": {"driveId": "drive-e2e", "id": "root"}}
                for suffix, name in (("a", "Invoices"), ("b", "Archive"))
            ])
        if re.fullmatch(r'v1.0/me/drive/items/folder-[ab]/children', path):
            return jsonify(value=[])
    match = re.fullmatch(r'v1.0/drives/drive-e2e/items/(folder-[ab]):/(.+):/content', path)
    if request.method == 'PUT' and match:
        if state['upload_error']:
            return jsonify(error={"code": "serviceNotAvailable", "message": "Simulated upload outage"}), 503
        content = request.get_data()
        if not content.startswith(b'%PDF-'):
            return jsonify(error='Expected a real PDF upload'), 400
        upload_id = uuid.uuid4().hex
        folder, name = match.groups()
        with lock:
            payloads[upload_id] = content
            state['uploads'].append({"id": upload_id, "folder": folder, "name": name, "size": len(content)})
        return jsonify(id=upload_id, name=name, webUrl=f'https://onedrive.example.test/{folder}/{name}'), 201
    return jsonify(error=f'Unexpected Graph request: {request.method} {path}'), 501


@app.get('/uploads/<upload_id>')
def download(upload_id):
    with lock:
        content = payloads.get(upload_id)
    if content is None:
        return Response(status=404)
    return send_file(io.BytesIO(content), mimetype='application/pdf')


@app.post('/openai/v1/responses')
def openai_response():
    if request.headers.get('Authorization') != 'Bearer sk-e2e-not-a-real-key-00000000':
        return jsonify(error={"message": "Unknown test key", "type": "invalid_request_error"}), 401
    body = request.get_json()
    if state['openai_error']:
        return jsonify(error={"message": "Simulated OpenAI outage", "type": "server_error", "code": "server_error"}), 500
    text = 'it works' if body['input'] == "Please respond with the words 'it works'" else 'E2E_document'
    return jsonify(
        id='resp_e2e', object='response', created_at=1, status='completed', model=body['model'],
        output=[{"id": "msg_e2e", "type": "message", "role": "assistant", "status": "completed",
                 "content": [{"type": "output_text", "text": text, "annotations": []}]}],
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, threaded=True)
