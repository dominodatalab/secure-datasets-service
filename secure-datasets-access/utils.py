import json
import os
import shutil
from datetime import datetime
import time
import random

import requests
import logging
import jwt

from urllib.parse import urljoin
import jproperties


logger = logging.getLogger("secure-ds-api")

WHO_AM_I_ENDPOINT = "v4/auth/principal"
DEFAULT_DOMINO_NUCLEUS_URI = "http://nucleus-frontend.domino-platform:80"
DOMINO_NUCLEUS_URI = os.environ.get("DOMINO_API_HOST",DEFAULT_DOMINO_NUCLEUS_URI)

#This helps with testing
ROOT_FOLDER_PREFIX= os.getenv("ROOT_FOLDER_PREFIX",'')
DATASETS_DATA_FOLDER=f"domino/datasets/filecache"
DATASETS_TARGET_DATA_FOLDER=f"secure/datasets/data"
DATASETS_TARGET_METADATA_FOLDER=f"secure/datasets/metadata"


DATASETS_ENDPOINT=f"{DOMINO_NUCLEUS_URI}/v4/datasetrw/dataset"
DATASETS_V2_ENDPOINT=f"{DOMINO_NUCLEUS_URI}/v4/datasetrw/datasets-v2"

DATASET_SNAPSHOT_ENDPOINT=f"{DOMINO_NUCLEUS_URI}/v4/datasetrw/snapshot"


id_by_domino_user_name={}

ENV_DEV="dev"
ENV_DEV_TEST="dev-test"
ENV_TEST="test"
ENV_PROD="prod"
SA_TO_ENV_MAPPING_FILE='/etc/config/sa-to-env-mapping.properties'
def regenerate_request_headers(headers):
    new_headers = {}
    if "Authorization" in headers:
        new_headers["Authorization"] = headers["Authorization"]
    if "X-Domino-Api-Key" in headers:
        new_headers["X-Domino-Api-Key"] = headers["X-Domino-Api-Key"]
    return new_headers

def get_env(headers):
    new_headers = regenerate_request_headers(headers)
    url: str = urljoin(DOMINO_NUCLEUS_URI, WHO_AM_I_ENDPOINT)
    resp = requests.get(url, headers=new_headers)
    env = "dev-wks"
    if resp.status_code == 200:
        user: str = resp.json()
        if user["isAnonymous"]:
            status_message = 'Anonymous user returned. Token not valid'
            return ENV_DEV, status_message
        else:
            user_name: str = user["canonicalName"]
            configs = jproperties.Properties()
            # Read the properties file
            with open(f'{ROOT_FOLDER_PREFIX}{SA_TO_ENV_MAPPING_FILE}', 'rb') as config_file:
                configs.load(config_file)
            env = configs.get(user_name).data if configs.get(user_name) else env
    else:
        logger.warning(f'Error fetching env {resp.status_code} with error message {resp.text}')
    return env

def access_control_permitted(headers,dataset_id,domino_username):
    allowed = False
    new_headers = regenerate_request_headers(headers)
    out = {}
    authorized, workload_owner = is_workload_owner_valid(new_headers)
    if authorized:
        workload_owner_access, calling_user_access = is_read_dataset_allowed(new_headers, dataset_id,
                                                                             workload_owner, domino_username)

        out['dataset_id'] = dataset_id
        out['app_owner'] = {'username': workload_owner, 'can_read': workload_owner_access}
        out['calling_user'] = {'username': domino_username, 'can_read': calling_user_access}

        if workload_owner_access and calling_user_access:
            allowed = True
    return allowed,out

def list_datasets(headers):
    new_headers = regenerate_request_headers(headers)
    resp = requests.get(DATASETS_V2_ENDPOINT,headers=new_headers)
    if resp.status_code==200:
        return resp.json()
    else:
        logger.error(resp.text)
        return [resp.text]

def get_rwsnapshot_id_dataset_id(headers):
    all_datasets={}
    datasets = list_datasets(headers)
    for d in datasets:
        ds_id = d['datasetRwDto']['id']
        snap_id = d['datasetRwDto']['readWriteSnapshotId']
        all_datasets[ds_id] = snap_id
    return all_datasets

def get_resource_path(headers,dataset_id):
    new_headers = regenerate_request_headers(headers)
    all_datasets = get_rwsnapshot_id_dataset_id(new_headers)
    if dataset_id in all_datasets:
        s_id = all_datasets[dataset_id]
        url = f"{DATASET_SNAPSHOT_ENDPOINT}/{s_id}"
        resp = requests.get(url, headers=new_headers)
        if resp.status_code == 200:
            j = resp.json()
            return j['snapshot']['resource']['resourceId']
    return ''

def create_response_json_for_calling_user_not_populated():
    out = {'success_file_found': False,
           'source_path': '',
           'local_path': '',
           'expires_on': ''}
    out['status_code'] = 403
    out['status'] = f'domino_username not provided'
    return out

def get_dataset_contents(workload_owner,calling_user,resource_path,object_sub_path,ttl=300)->str:

    destination_path = f"{ROOT_FOLDER_PREFIX}/{DATASETS_TARGET_DATA_FOLDER}/{workload_owner}/{calling_user}"
    metadata_path = f"{ROOT_FOLDER_PREFIX}/{DATASETS_TARGET_METADATA_FOLDER}/{workload_owner}/{calling_user}"
    if not os.path.exists(destination_path):
        os.makedirs(destination_path,exist_ok=True)
    if not os.path.exists(metadata_path):
        os.makedirs(metadata_path, exist_ok=True)
    epoch_time = int(datetime.utcnow().timestamp())
    random_number = random.randint(1, 1000000)
    object_path = f"{ROOT_FOLDER_PREFIX}/{DATASETS_DATA_FOLDER}/{resource_path}/{object_sub_path}"

    target_file_path = ''

    file_found = True
    if os.path.exists(object_path):
        file_components= os.path.splitext(object_path)
        file_extension=''
        if len(file_components)>1:
            extension = file_components[1]
            file_extension=f'{extension}'
        target_file_path = os.path.join(destination_path, f"{epoch_time}-{random_number}{file_extension}")
        target_metadata_path = os.path.join(metadata_path, f"{epoch_time}-{random_number}.json")
        shutil.copy(object_path, target_file_path)

        logger.warning(f'Writing to data location {target_file_path}')
        logger.warning(f'Writing to metadata location {target_metadata_path}')
        print(f'Writing to data location {target_file_path}')
        print(f'Writing to metadata location {target_metadata_path}')
        expiry_epoch_time = datetime.utcnow().timestamp() + ttl
        with open(target_metadata_path, 'w') as f:
            json.dump({'expires':expiry_epoch_time,'local_data_file':target_file_path},f)
    else:
        file_found=False
    format_str = "%Y-%m-%d %H:%M:%S"

    dt = datetime.utcfromtimestamp(expiry_epoch_time)
    return {'success_file_found' : file_found,
            'source_path': object_path,
            'local_path':target_file_path,
            'expires_on': dt.strftime(format_str)}

def is_workload_owner_valid(headers):
    url: str = urljoin(DOMINO_NUCLEUS_URI, WHO_AM_I_ENDPOINT)
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        user: str = resp.json()
        if user["isAnonymous"]:
            status_message = 'Anonymous user returned. Token not valid'
            return False, status_message
        user_name: str = user["canonicalName"]
        logger.warning(f"Extended API Invoking User {user_name}")
        return True, user_name
    else:
        return False, {'error':resp.text}


def get_dataset_grants(headers,dataset_id):
    new_headers = regenerate_request_headers(headers)
    url = f"{DATASETS_ENDPOINT}/{dataset_id}/grants"

    print(url)
    resp = requests.get(url,headers=new_headers)

    if (resp.status_code == 200):
        return resp.json()
    else:
        print(resp.text)
        print(f"Error invoking get_dataset_grants. Status Code {resp.status_code}")
        logger.warning(f"Error invoking get_dataset_grants. Status Code {resp.status_code}")


def is_read_dataset_allowed(headers, dataset_id, workload_owner,caller_domino_user):
    workload_owner_read_allowed = False
    caller_read_allowed = False
    grants = get_dataset_grants(headers,dataset_id)
    if not grants:
        grants = []
    for g in grants:
        if g['targetName'] == workload_owner:
            if g['targetRole'] in ['DatasetRwOwner','DatasetRwEditor','DatasetRwReader']:
                workload_owner_read_allowed=True
        if g['targetName'] == caller_domino_user:
            if g['targetRole'] in ['DatasetRwOwner','DatasetRwEditor','DatasetRwReader']:
                caller_read_allowed=True

    return (workload_owner_read_allowed,caller_read_allowed)


def is_past_epoch_datetime(epoch_time):
    # Get current time
    current_time = datetime.utcnow()
    # Convert epoch time to datetime object
    epoch_datetime = datetime.utcfromtimestamp(epoch_time)
    # Compare current time with epoch datetime
    return current_time > epoch_datetime


def list_path_for_dataset(dataset_id,resource_path,path=""):
    file_contents=[]
    results = {
                "dataset-id":dataset_id,
                "path":path
               }
    object_path = f"{ROOT_FOLDER_PREFIX}/{DATASETS_DATA_FOLDER}/{resource_path}/{path}"
    if os.path.exists(object_path):
        if os.path.isdir(object_path):
            contents = os.listdir(object_path)
            # Iterate through each item in the directory
            for item in contents:
                # Construct the full path to the item
                item_path = os.path.join(object_path, item)
                # Check if the item is a file or a directory
                if os.path.isfile(item_path):
                    file_contents.append({"name":item, "type":"file"})
                elif os.path.isdir(item_path):
                    file_contents.append({"name":item, "type":"folder"})
                else:
                    file_contents.append({"name":item, "type":"na"})
            results['success'] = True
            results['contents'] = file_contents
        else:
            results['success'] = False
            results['contents'] = [f"Path {path} is a file. Can only list folder"]
    else:
        results['success'] = False
        results['contents'] = [f"Path {path} does not exist for dataset {dataset_id}"]

    return results



def get_object_paths_to_delete():
    object_paths_to_delete = []
    data_folder = f"{ROOT_FOLDER_PREFIX}/{DATASETS_TARGET_DATA_FOLDER}"
    metadata_folder = f"{ROOT_FOLDER_PREFIX}/{DATASETS_TARGET_METADATA_FOLDER}"
    if os.path.exists(metadata_folder):
        owner_user_folders = os.listdir(metadata_folder)
        for ou in owner_user_folders:
            owner_metadata_folder = os.path.join(metadata_folder,ou)
            logger.warning(f'Owner Folder {owner_metadata_folder}')
            calling_user_folders =  os.listdir(owner_metadata_folder)
            for cu in calling_user_folders:
                calling_user_folder = os.path.join(owner_metadata_folder, cu)
                logger.warning(f'Calling User Folder {calling_user_folder}')
                files = os.listdir(calling_user_folder)
                for f in files:
                    metadata_path = os.path.join(calling_user_folder,f)
                    with open(metadata_path) as file:
                        metadata = json.load(file)
                        expiry_epoch_time = metadata['expires']

                        current_epoch_time = datetime.utcnow().timestamp()
                        if expiry_epoch_time < current_epoch_time:
                            if 'local_data_file' in metadata:
                                file_to_delete_path = metadata['local_data_file']
                                object_paths_to_delete.append((metadata_path,file_to_delete_path))
                            else:
                                file_to_delete = os.path.splitext(f)[0]
                                file_to_delete_path = os.path.join(data_folder, ou, cu, file_to_delete)
                                metadata_file_to_delete = os.path.join(metadata_folder, ou, cu, file_to_delete)
                                object_paths_to_delete.append((metadata_file_to_delete, file_to_delete_path))

     else:
        logger.warning(f'Folder {metadata_folder} does not exist')
    return object_paths_to_delete

def cleanup_expired_objects():
    while(True):
        objects_to_delete = get_object_paths_to_delete()
        delete_objects(objects_to_delete)
        sleep_interval = 60
        print(f"Sleeping for {sleep_interval} seconds")
        time.sleep(sleep_interval)

def delete_objects(objects_to_delete):
    try:
        for o in objects_to_delete:
            metadata = o[0]
            data = o[1]
            print(f'Deleting {metadata} and associated data file {data}')
            if os.path.exists(data):
                print(f'Found data file {data} - Deleting')
                os.remove(data)
            if os.path.exists(metadata):
                print(f'Found metadata file {metadata} - Deleting')
                os.remove(metadata)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    os.environ['DOMINO_API_HOST']='https://prod-field.cs.domino.tech/'
    os.environ['ROOT_FOLDER_PREFIX'] = '/Users/sameerwadkar/Documents/GitHub2/secure-dataset-access-service/root-folder'
    ROOT_FOLDER_PREFIX = os.getenv("ROOT_FOLDER_PREFIX", '')

    '''
    print(is_user_authorized(headers))

    dataset_id='626981f5302ba33a1f36082d'
    domino_user_name = 'data_test'
    print(is_permitted_to_read_dataset(headers,dataset_id,domino_user_name))
    resource_path = get_resource_path(headers,dataset_id)

    out = get_dataset_contents(domino_user_name,resource_path,"/sample/test.txt",duration=300)
    print(out)

    print(datetime.utcnow().timestamp())
    '''

