import json
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Suppress SSL warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Configuration
CONFIG_FILE = "config.json"
IP_LIST_FILE = "ip_list.txt"
TIMEOUT = 2  # 2 seconds timeout
MAX_WORKERS = 10  # Process 10 servers at a time

def load_config():
    """Load configuration from config.json"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return None

def load_ip_list():
    """Load IP list from file"""
    try:
        with open(IP_LIST_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error loading IP list: {e}")
        return []

def login_ilo(ip, username, password):
    """Login to iLO and return session ID and session URI"""
    url = f"https://{ip}/rest/v1/SessionService/Sessions"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "UserName": username,
        "Password": password
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, verify=False, timeout=TIMEOUT)
        if response.status_code == 201:
            session_id = response.headers['X-Auth-Token']
            # Extract session URI from response
            session_uri = response.json().get('OdataId', None) or response.json().get('@odata.id', None)
            return session_id, session_uri
        else:
            print(f"Login failed for {ip}: {response.status_code}")
            return None, None
    except requests.Timeout:
        print(f"Login timeout for {ip}")
        return None, None
    except Exception as e:
        print(f"Login error for {ip}: {e}")
        return None, None

def logout_ilo(ip, session_id, session_uri):
    """Logout from iLO session"""
    if not session_id or not session_uri:
        print(f"Cannot logout from {ip}: Missing session ID or URI")
        return
    
    url = f"https://{ip}{session_uri}"
    headers = {'X-Auth-Token': session_id}
    
    try:
        response = requests.delete(url, headers=headers, verify=False, timeout=TIMEOUT)
        if response.status_code == 200:
            print(f"Logged out successfully from {ip}")
        else:
            print(f"Logout failed for {ip}: {response.status_code} - {response.text}")
    except requests.Timeout:
        print(f"Logout timeout for {ip}")
    except Exception as e:
        print(f"Logout error for {ip}: {e}")

def get_users(ip, session_id):
    """Get existing users"""
    url = f"https://{ip}/rest/v1/AccountService/Accounts"
    headers = {'X-Auth-Token': session_id}
    
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=TIMEOUT)
        if response.status_code == 200:
            return response.json()['Items']
        return []
    except requests.Timeout:
        print(f"Get users timeout for {ip}")
        return []
    except Exception as e:
        print(f"Error getting users for {ip}: {e}")
        return []

def delete_user(ip, session_id, username):
    """Delete the specified user"""
    url = f"https://{ip}/rest/v1/AccountService/Accounts"
    headers = {'X-Auth-Token': session_id}
    
    # Check if user exists
    users = get_users(ip, session_id)
    user_exists = False
    user_id = None
    
    for user in users:
        if user['UserName'] == username:
            user_exists = True
            user_id = user['Id']
            break
    
    if not user_exists:
        print(f"User {username} not found on {ip}. Skipping deletion.")
        return
    
    try:
        # Delete the user
        delete_url = f"{url}/{user_id}"
        response = requests.delete(delete_url, headers=headers, verify=False, timeout=TIMEOUT)
        
        if response.status_code == 200:
            print(f"Deleted user {username} on {ip} successfully")
        else:
            print(f"Failed to delete user {username} on {ip}: {response.status_code} - {response.text}")
    except requests.Timeout:
        print(f"Delete user operation timeout for {ip}")
    except Exception as e:
        print(f"Error deleting user {username} on {ip}: {e}")

def process_server(ip, login_username, login_password, username):
    """Process a single server"""
    print(f"Processing {ip}")
    # Login and get both session ID and session URI
    session_id, session_uri = login_ilo(ip, login_username, login_password)
    if session_id:
        try:
            # Delete the user
            delete_user(ip, session_id, username)
        finally:
            # Always attempt to logout, even if user deletion fails
            logout_ilo(ip, session_id, session_uri)

def main():
    # Load configuration
    config = load_config()
    if not config:
        return
    
    login_username = config.get('login_username')
    login_password = config.get('login_password')
    username = config.get('new_username')  # Reusing 'new_username' field for the user to delete
    
    if not all([login_username, login_password, username]):
        print("Missing required configuration parameters")
        return
    
    # Load IP list
    ip_list = load_ip_list()
    if not ip_list:
        print("No IPs found in list")
        return
    
    # Process servers in parallel
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(
                process_server,
                ip,
                login_username,
                login_password,
                username
            )
            for ip in ip_list
        ]
        
        # Wait for all tasks to complete
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f"Thread execution error: {e}")
    
    print("\nProcessing complete")

if __name__ == "__main__":
    start_time = time.time()
    main()
    print(f"Total execution time: {time.time() - start_time:.2f} seconds")
