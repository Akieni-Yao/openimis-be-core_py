import requests

# Define the token API endpoint and headers
TOKEN_API_URL = "https://dms.akieni.com/backend/cnss/oauth/token"
TOKEN_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Authorization': 'Basic a2l5YXM6WUAxMjMkJV4yMyo=',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://dms.akieni.com',
    'Referer': 'https://dms.akieni.com/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="117", "Not;A=Brand";v="8", "Chromium";v="117"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': 'Windows',
}

# Define the data for token request
TOKEN_DATA = {
    'username': 'lakshya.soni',
    'password': 'Laks@5500',
    'grant_type': 'password',
    'scope': 'read',
}


# Function to generate and return the access token
def generate_dms_access_token():
    response = requests.post(TOKEN_API_URL, headers=TOKEN_HEADERS, data=TOKEN_DATA, verify=False)
    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data.get('access_token')
        print(f'Access Token: {access_token}')
        return access_token
    else:
        print(f'Error obtaining access token: {response.status_code} - {response.text}')
        return None


# Obtain the access token
access_token = generate_dms_access_token()

# Check if the access token was obtained successfully
if access_token:
    # Define your other API endpoints with the access token in the headers
    BASE_API_URL = "https://dms.akieni.com/backend/cnss"

    CNSS_CREATE_FOLDER_API_URL = f"{BASE_API_URL}/folder/create"
    CNSS_CREATE_FILE_API_URL = f"{BASE_API_URL}/file/create"
    CNSS_UPDATE_FILE_API_URL = f"{BASE_API_URL}/file/update"
    CNSS_DOCUMENT_SEARCH_API_URL = f"{BASE_API_URL}/documents/get"
    CNSS_ALL_DOCUMENT_SEARCH_API_URL = f"{BASE_API_URL}/document/search"
    CNSS_SAVE_ALL_DOCUMENT_URL = f"{BASE_API_URL}/document/"
    CNSS_SAVE_DOCUMENT_SYNC = "http://localhost:9001/cnss/document/saveDocument?tempCamuNumber="

    HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Authorization": f"Bearer {access_token}",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "Origin": "https://dms.akieni.com",
        "Referer": "https://dms.akieni.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="117", "Not;A=Brand";v="8", "Chromium";v="117"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "Windows",
    }
