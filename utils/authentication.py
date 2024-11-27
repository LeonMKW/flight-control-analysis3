import requests


def get_header_token(post_token_url, post_token_user_name, post_token_password):
    payload = {
        "username": post_token_user_name,
        "password": post_token_password,
        "loginType": 2
    }
    response = requests.post(post_token_url, json=payload)
    response_data = response.json()

    token = response_data.get('data', {}).get('token')
    return token
