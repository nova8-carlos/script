import os
import requests

def auth_identity(checkmarx_url, checkmarx_username, checkmarx_password, checkmarx_client_secret):
    print("Auth method to get the access token...")
    auth_endpoint = f"{checkmarx_url}/cxrestapi/auth/identity/connect/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "username": checkmarx_username,
        "password": checkmarx_password,
        "grant_type": "password",
        "scope": "access_control_api sast_api",
        "client_id": "resource_owner_sast_client",
        "client_secret": checkmarx_client_secret
    }


if __name__ == "__main__":
    print(auth_identity())
