import os
import sys
from flask import Flask, request, make_response, Response, jsonify  # type: ignore
import logging
import utils



WHO_AM_I_ENDPOINT = "v4/auth/principal"
DATASETS_V2 = "v4/datasetrw/datasets-v2"

logger = logging.getLogger("extended-api")
app = Flask(__name__)

@app.route("/dataset/all", methods=["GET"])
def get_all_datasets():
    all_datasets = utils.list_datasets(request.headers)
    return {'all_datasets':all_datasets}

@app.route("/dataset/canread/<dataset_id>", methods=["GET"])
def verify_access(dataset_id)->str:
    domino_username = request.headers.get('domino-username')
    access_allowed = False
    out = {}
    if domino_username:
        access_allowed, out = utils.access_control_permitted(request.headers,dataset_id,domino_username)
        status_code=200
    if not access_allowed:
        status_code=403
        out['status_code'] = status_code
    return make_response(out, status_code)

@app.route("/dataset/list/<dataset_id>", methods=["GET"])
def dir_list_dataset(dataset_id):
    domino_username = request.headers.get('domino-username')
    access_allowed = False
    out = {}
    if domino_username:
        access_allowed, out = utils.access_control_permitted(request.headers,dataset_id,domino_username)

    if access_allowed:
        path = request.args['path']
        resource_path = utils.get_resource_path(request.headers, dataset_id)
        out = utils.list_path_for_dataset(dataset_id, resource_path, path)
        out['status_code'] = 200
        out['status'] = "Success"
        return make_response(out,200)
    else:
        out['status_code'] = 403
        out['status'] = "Dataset Access not permitted for either the App Owner or App Caller"
        return make_response(out,
                             403)
@app.route("/dataset/fetch/<dataset_id>", methods=["GET"])
def get_dataset_contents(dataset_id)->str:

    domino_username = request.headers.get('domino-username')
    out = {}
    if domino_username:
        allowed, out = utils.access_control_permitted(request.headers, dataset_id,domino_username)

        new_headers = utils.regenerate_request_headers(request.headers)
        authorized, workload_owner = utils.is_workload_owner_valid(new_headers)
        if allowed:
            calling_user = request.headers['domino-username']
            object_sub_path = request.args['path']
            ttl = 300
            env = utils.get_env(request.headers)
            if ttl in request.args:
                ttl = int(request.args['ttl'])
            resource_path = utils.get_resource_path(new_headers, dataset_id)
            out = utils.get_dataset_contents(workload_owner=workload_owner,calling_user=calling_user,
                                             resource_path=resource_path,
                                             object_sub_path=object_sub_path, ttl=ttl)
            out['status_code'] = 200
            out['status'] = 'Success'
            return make_response(out, 200)
        else:
            out['status_code'] = 403
            out['status'] = 'Access to the requested object not permitted'
            return make_response(out, 403)
    else:
        out['status_code'] = 403
        out['status'] = f'domino-username not contained in the request headers'
        return make_response(out, 403)


@app.route("/healthz")
def alive():
    return "{'status': 'Healthy'}"


def create_app():
    log = logging.getLogger("werkzeug")
    lvl = logging.getLevelName(os.environ.get("LOG_LEVEL", "WARNING").upper())
    log.setLevel(lvl)
    return app

if __name__ == "__main__":
    is_local = os.environ.get('LOCAL_EXECUTION',"false")=="true"
    is_cleanup_container = os.environ.get('IS_CLEANUP_CONTAINER',"false")=="true"
    if is_cleanup_container:
        utils.cleanup_expired_objects()
    else:
        debug = os.environ.get("FLASK_ENV") == "development"
        if is_local:
            create_app().run(
                host=os.environ.get("FLASK_HOST", "0.0.0.0"),
                port=6000,
                debug=debug,
                #ssl_context=("/ssl/tls.crt", "/ssl/tls.key"),
            )
        else:
            create_app().run(
                host=os.environ.get("FLASK_HOST", "0.0.0.0"),
                port=6000,
                debug=debug,
                ssl_context=("/ssl/tls.crt", "/ssl/tls.key"),
            )
