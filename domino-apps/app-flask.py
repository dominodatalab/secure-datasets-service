import subprocess

# This is a sample Python/Flask app showing Domino's App publishing functionality.
# You can publish an app by clicking on "Publish" and selecting "App" in your
# quick-start project.

import json
import flask
from flask import request, redirect, url_for
from flask import Flask, render_template
import numpy as np


class ReverseProxied(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]
        # Setting wsgi.url_scheme from Headers set by proxy before app
        scheme = environ.get('HTTP_X_SCHEME', 'https')
        if scheme:
            environ['wsgi.url_scheme'] = scheme
        # Setting HTTP_HOST from Headers set by proxy before app
        remote_host = environ.get('HTTP_X_FORWARDED_HOST', '')
        remote_port = environ.get('HTTP_X_FORWARDED_PORT', '')
        if remote_host and remote_port:
            environ['HTTP_HOST'] = f'{remote_host}:{remote_port}'
        return self.app(environ, start_response)


app = flask.Flask(__name__)
app.wsgi_app = ReverseProxied(app.wsgi_app)


# Homepage which uses a template file
# @app.route('/')
# def index_page():
#  return flask.render_template("index.html")

# Sample redirect using url_for
# @app.route('/redirect_test')
# def redirect_test():
#  return redirect( url_for('another_page') )

# Sample return string instead of using template file
@app.route('/another_page')
def another_page():
    msg = "You made it with redirect( url_for('another_page') )." + \
          "A call to flask's url_for('index_page') returns " + url_for('index_page') + "."
    return msg


@app.route("/random")
@app.route("/random/<int:n>")
def random(n=100):
    random_numbers = list(np.random.random(n))
    return json.dumps(random_numbers)


import os
import requests


def get_token():
    # Fetch the mounted service account token
    uri = os.environ['DOMINO_API_PROXY']
    return requests.get(f"{uri}/access-token").text


def get_all_datasets():
    sa_token = get_token()
    my_headers = {"Authorization": f"Bearer {sa_token}"}
    domino_api_host = os.environ['DOMINO_API_HOST']

    url = f"{domino_api_host}/v4/datasetrw/datasets-v2"
    response = requests.get(url, headers=my_headers)
    if response.status_code == 200:
        print("All datasets")
        datasets = response.json()
        json_formatted_str = json.dumps(datasets, indent=2)
        # print(json_formatted_str)
        ret = []
        for d in datasets:
            id = d['datasetRwDto']['id']
            name = d['datasetRwDto']['name']
            ret.append({'id': id, 'name': name})
    else:
        print(f"Error - Response Code {response.status_code}, message = {response.text} ")

    return ret


def get_grants_for_dataset(dataset_id):
    sa_token = get_token()
    my_headers = {"Authorization": f"Bearer {sa_token}"}
    domino_api_host = os.environ['DOMINO_API_HOST']
    url = f"{domino_api_host}/v4/datasetrw/dataset/{dataset_id}/grants"
    response = requests.get(url, headers=my_headers)
    return response


def get_datasets_with_entitlements():
    ret = get_all_datasets()
    ds_entititlements = []
    for d in ret:
        dataset_id = d['id']
        grants_response = get_grants_for_dataset(dataset_id)
        ds_grants = []
        if grants_response.status_code == 200:
            all_grants = grants_response.json()
            # print(f'Grants for {dataset_id}')
            # print(all_grants)

            for g in all_grants:
                t_name = g['targetName']
                t_role = g['targetRole']
                t_is_org = g['isOrganization']
                ds_grants.append({'user_name': t_name, 'role': t_role, 'is_org': t_is_org})
                d['grants'] = ds_grants
            ds_entititlements.append(d)
        else:
            print(f"Error - Response Code {grants_response.status_code}, message = {grants_response.text} ")
            d['grants'] = ds_grants
            ds_entititlements.append(d)
    return ds_entititlements


# Now fetch each
def verify_dataset_access(domino_user_name, dataset_id, object_name="/a/b/c/ds.txt"):
    sa_token = get_token()
    my_headers = {"Authorization": f"Bearer {sa_token}",
                  "domino-username": domino_user_name,
                  "ttl": "300"
                  }

    service_name = "secure-datasets-svc"
    params = {"path": object_name}
    endpoint = f"dataset/fetch/{dataset_id}"
    service_name = "secure-datasets-svc"
    dns_name = f"{service_name}.domino-compute.svc.cluster.local"

    url = f"https://{dns_name}/{endpoint}"

    r = requests.get(url, params=params, headers=my_headers, verify=False)
    s_code = r.status_code
    out = {}
    print(r.text)
    if (s_code == 200):
        out = r.json()

        if out['success_file_found'] == True:
            print(f"Successfully read {object_name} from dataset {dataset_id}")
            t_file = out['local_path']
            contents = ""
            with open(t_file, 'r') as file:
                # Read the entire file content into a variable
                contents = file.read()
                print(contents)
            out["contents"] = contents
        else:
            print('Object not found')
            out["contents"] = ''
    else:
        out['contents'] = r.text
        out['s_code'] = s_code
        out = r.json()
        # print(f"Could not read {object_name} from dataset {dataset_id} : Status code {s_code}")

    return out


# @app.route("/dsaccess")
def dsaccess(domino_user_name):
    # Now, file_content variable holds the content of the file
    # domino_user_name = request.headers.get("domino-username")
    object_path = "/a/b/c/ds.txt"
    ds = get_all_datasets()
    results = []
    for d in ds:
        id = d['id']
        name = d['name']
        out = verify_dataset_access(domino_user_name, id, "a/b/c/ds.txt")
        out['dataset_name'] = name
        out['name'] = name
        results.append(out)
    return results


def get_listing(dataset_id, domino_user_name, path):
    service_name = "secure-datasets-svc"
    dns_name = f"{service_name}.domino-compute.svc.cluster.local"

    sa_token = get_token()
    my_headers = {"Authorization": f"Bearer {sa_token}", "domino-username": domino_user_name}
    params = {"path": path}
    endpoint = f"dataset/list/{dataset_id}"
    url = f"https://{service_name}/{endpoint}"
    r = requests.get(url, params=params, headers=my_headers, verify=False)
    out = {}

    out['domino_user_name'] = domino_user_name
    out['dataset_id'] = dataset_id
    out['path'] = f"/{path}"

    if (r.status_code == 200):
        j = r.json()

        out['contents'] = j['contents']
        out['status_code'] = j['status_code']
        out['status'] = j['status']
    else:
        j = r.json()
        out['contents'] = ''
        out['status_code'] = j['status_code']
        out['status'] = j['status']

    return out


def dslisting(domino_user_name):
    # Now, file_content variable holds the content of the file
    # domino_user_name = request.headers.get("domino-username")
    # object_path="/a/b/c/ds.txt"
    ds = get_all_datasets()
    results = []

    for d in ds:
        id = d['id']
        name = d['name']
        out = get_listing(id, domino_user_name, "")

        results.append(out)
    return results


@app.route('/')
def display_nested_table():
    domino_user_name = request.headers.get('domino-username')
    # Set the title of the webpage to the user name
    title = f"Calling user {domino_user_name}."

    json_data = get_datasets_with_entitlements()
    results = dsaccess(domino_user_name)

    listing = dslisting(domino_user_name)
    print(request.headers)
    print('xxx')
    print(listing)
    return flask.render_template('index.html', data=json_data, title=domino_user_name, results=results, listing=listing)


