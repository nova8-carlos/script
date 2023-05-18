import os
import subprocess
import requests
import json


print("Validating envs!")

required_envs = [
    "GITHUB_TOKEN",
    "CHECKMARX_URL",
    "CHECKMARX_USERNAME",
    "CHECKMARX_PASSWORD",
    "CHECKMARX_CLIENT_SECRET",
    "CHECKMARX_PRESET",
    "CHECKMARX_TEAM"
]

for env in required_envs:
    if env not in os.environ:
        print(f"Missing {env} environment")
        exit(1)

print("Set up the initials envs of the context")
PARAMETER_SYMBOLIC_FILES = ""

symbolic_files = subprocess.check_output(["find", ".", "-type", "l"]).decode().strip()
if symbolic_files:
    PARAMETER_SYMBOLIC_FILES = ",".join(symbolic_files.split())

# Checkmarx API - Auth method
def auth_identity():
    print("Auth method to get the access token...")
    auth_url = f"{os.environ['CHECKMARX_URL']}/cxrestapi/auth/identity/connect/token"
    auth_data = {
        "username": os.environ['CHECKMARX_USERNAME'],
        "password": os.environ['CHECKMARX_PASSWORD'],
        "grant_type": "password",
        "scope": "access_control_api sast_api",
        "client_id": "resource_owner_sast_client",
        "client_secret": os.environ['CHECKMARX_CLIENT_SECRET']
    }

    response = requests.post(auth_url, data=auth_data)
    auth_response = response.json()
    bearer_token = auth_response.get('access_token')

    if bearer_token is None:
        print(f"Auth failed: {auth_response}")
        exit(1)
    print("Auth success!")
    return bearer_token

# Checkmarx API - create_branch method
def create_branch(project_id, branch_name):
    print(f"Creating project branch: {branch_name} for project ID: {project_id}")
    create_branch_url = f"{os.environ['CHECKMARX_URL']}/cxrestapi/projects/{project_id}/branch"
    create_branch_data = {
        "name": branch_name
    }

    response = requests.post(create_branch_url, json=create_branch_data, headers={"Authorization": f"Bearer {bearer_token}"})
    create_branch_response = response.json()

    print("Request create branch executed with success, validating response.")
    if 'id' not in create_branch_response:
        print(f"Branch could not be created: {create_branch_response}")
        exit(1)
    print(f"Branch created with success! {create_branch_response}")

# Checkmarx API - delete_branch method
def delete_branch(project_id):
    print(f"Deleting project ID: {project_id}")
    delete_branch_url = f"{os.environ['CHECKMARX_URL']}/cxrestapi/help/projects/{project_id}"
    delete_branch_data = {
        "deleteRunningScans": "true"
    }

    response = requests.delete(delete_branch_url, json=delete_branch_data, headers={"Authorization": f"Bearer {bearer_token}"})
    delete_branch_response = response.json()

    print(f"Branch deleted with success! {delete_branch_response}")

# Local helper function to compare branch list to be excluded from Checkmarx
def search_branches_to_delete_in_checkmarx():
    print("Validating HEAD_BRANCH_NAME env!")
    if 'HEAD_BRANCH_NAME' not in os.environ:
        print("Missing HEAD_BRANCH_NAME environment")
        exit(1)

    print("Searching for branches to delete in Checkmarx")
    git_config_command = ["git", "config", "--global", "--add", "safe.directory", "*"]
    subprocess.run(git_config_command)

    all_branches = subprocess.check_output(["git", "branch", "--list", "--remotes"]).decode().strip()
    branch_list = [branch.split("origin/")[-1] for branch in all_branches.split() if branch.split("origin/")[-1] != os.environ['HEAD_BRANCH_NAME']]
    branch_list_sanitized = [branch.replace("/", "-").replace("_", "-").lower() for branch in branch_list]
    checkmarx_local_projects = [project for project in PROJECT_LIST if project.split(" ")[-1].split(".")[-1] != os.environ['HEAD_BRANCH_NAME']]

    if branch_list and checkmarx_local_projects:
        print('''
  =============================================
  github branch names sanitized:
  {}
  =============================================
  checkmarx projects:
  {}
  =============================================
  LOOPING TO FIND BRANCHES TO DELETE IN CHECKMARX....
        '''.format(branch_list_sanitized, checkmarx_local_projects))

        for line in checkmarx_local_projects:
            tmp = line.split(".")[-1][::-1].split(".", 1)[1][::-1]
            id = line.split(" ")[0]

            if tmp not in branch_list_sanitized:
                print(f"Branch: {tmp} not found. Deleting Checkmarx project ID: {id}")
                delete_branch(id)
            else:
                print(f"Branch {tmp} present in the list, all clear!")
    else:
        print("No branches to validate, skipping...")

# Checkmarx API - project_exists method
def get_projects():
    print("Getting project list...")
    get_projects_url = f"{os.environ['CHECKMARX_URL']}/cxrestapi/projects"
    
    response = requests.get(get_projects_url, headers={"Authorization": f"Bearer {bearer_token}"})
    get_projects_response = response.json()

    print(f"Projects list request executed with success, Searching for project: {os.environ['CIRCLE_PROJECT_REPONAME']}")
    print(f"with Branch: {PARAMETER_PROJECT_BRANCH_NAME}")

    project_list = get_projects_response

    for project in project_list:
        if project['name'] == os.environ['CIRCLE_PROJECT_REPONAME']:
            return project['id'], project['name']

        if project['name'] == PARAMETER_PROJECT_BRANCH_NAME:
            return project['id'], project['name']

    return None, None

# Checkmarx API - project_exists method
def project_exists():
    # Get project list
    project_id, project_name = get_projects()

    print("Project Type:", PROJECT_TYPE)
    if project_id:
        # Projeto Legado ou Novo + Existente
        THRESHOLDS_HIGH_CHECKMARX = "0"
        THRESHOLDS_MEDIUM_CHECKMARX = "0"
        print(f"Project Found: {project_name}. Verifying if branch: {PARAMETER_BRANCH_NAME_SANITIZED} exists.")

        if not project_exists(project_id, PARAMETER_PROJECT_BRANCH_NAME):
            print("Branch not found, trying to create one!")
            create_branch(project_id, PARAMETER_PROJECT_BRANCH_NAME)
        else:
            print(f"Branch already exists: {PARAMETER_PROJECT_BRANCH_NAME}")

        if any(project['name'].startswith(os.environ['CIRCLE_PROJECT_REPONAME']+".") for project in project_list):
            search_branches_to_delete_in_checkmarx()
    else:
        PARAMETER_PROJECT_BRANCH_NAME = os.environ['CIRCLE_PROJECT_REPONAME']
        if PROJECT_TYPE != "legacy":
            print("Set Thresholds")
            THRESHOLDS_HIGH_CHECKMARX = "0"
            THRESHOLDS_MEDIUM_CHECKMARX = "0"
        print("Project not found, ready to execute next step. The project listed is:")
        print(project_list)

# Checkmarx API - Get Last Scan ID
def get_last_scan_id():
    print("Deleting last scan ID - Sleep 5s")
    time.sleep(5)
    # Get project list
    project_id, _ = get_projects()

    print(f"Getting last scan ID for Project: {project_id}")
    get_last_scan_id_url = f"{os.environ['CHECKMARX_URL']}/Cxwebinterface/odata/v1/Projects/{project_id}"

    response = requests.get(get_last_scan_id_url, headers={"Authorization": f"Bearer {bearer_token}"})
    get_last_scan_id_response = response.json()

    print("Request last scan ID executed with success, validating response.")
    if 'value' not in get_last_scan_id_response or not get_last_scan_id_response['value']:
        print(f"Last scan ID not found: {get_last_scan_id_response}")
        exit(1)

    last_scan_id = get_last_scan_id_response['value'][0]['LastScanId']
    print(f"Last scan ID identified! {last_scan_id}")

    print("Calling delete last scan ID method!")
    delete_last_scan_id(last_scan_id)

# Checkmarx API - delete_last scan ID method
def delete_last_scan_id(last_scan_id):
    print(f"Deleting last scan ID project ID: {last_scan_id}")
    delete_last_scan_id_url = f"{os.environ['CHECKMARX_URL']}/cxrestapi/sast/scans/{last_scan_id}"
    delete_last_scan_id_data = {
        "deleteRunningScans": "true"
    }

    response = requests.delete(delete_last_scan_id_url, json=delete_last_scan_id_data, headers={"Authorization": f"Bearer {bearer_token}"})
    delete_last_scan_id_response = response.json()

    print(f"Last scan ID deleted with success! {delete_last_scan_id_response}")

###### Main ######

# Call authentication function
bearer_token = auth_identity()

# Function that executes
PARAMETER_METHODE()

print("Exporting context env to next steps")
# EXPORTING ENVS TO BE USED IN THE cxflow/scan command ============================================
with open(os.environ['BASH_ENV'], "a") as env_file:
    env_file.write(f"export PARAMETER_SYMBOLIC_FILES={PARAMETER_SYMBOLIC_FILES}\n")
    env_file.write(f"export PARAMETER_BRANCH_NAME_SANITIZED={PARAMETER_BRANCH_NAME_SANITIZED}\n")
    env_file.write(f"export PARAMETER_PROJECT_BRANCH_NAME={PARAMETER_PROJECT_BRANCH_NAME}\n")
    env_file.write(f"export PARAMETER_ADITIONAL_CHECKMARX_ARGS={PARAMETER_ADITIONAL_CHECKMARX_ARGS}\n")
    env_file.write(f"export THRESHOLDS_HIGH_CHECKMARX={THRESHOLDS_HIGH_CHECKMARX}\n")
    env_file.write(f"export THRESHOLDS_MEDIUM_CHECKMARX={THRESHOLDS_MEDIUM_CHECKMARX}\n")

print("Finished with success!!!")
