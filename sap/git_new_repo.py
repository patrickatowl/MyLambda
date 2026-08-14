 import time
import json
import jwt
import requests

# ==========================================
# 1. GitHub App 配置資訊
# ==========================================
APP_ID = "123456"  # 您的 GitHub App ID
ORGANIZATION_NAME = "your-company-org"  # 目標 Organization 名稱
PRIVATE_KEY_PATH = "your-app-private-key.pem"  # GitHub App 下載的私鑰路徑

# GitHub API Base URL
GITHUB_API_URL = "https://api.github.com"


# ==========================================
# 2. 核心函數：生成 App JWT (用於 Auth)
# ==========================================
def generate_jwt(app_id, private_key_path):
    """使用私鑰簽署 JWT，有效期限設定為 10 分鐘 (GitHub 限制最大 10 分鐘)"""
    with open(private_key_path, "r") as key_file:
        private_key = key_file.read()

    payload = {
        "iat": int(time.time()) - 60,  # 發行時間 (前推 60 秒防止時鐘偏差)
        "exp": int(time.time()) + (10 * 60),  # 過期時間 (10 分鐘)
        "iss": app_id,
    }

    # 使用 RS256 演算法簽署
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")
    return encoded_jwt


# ==========================================
# 3. 核心函數：取得 Organization 的 Installation Token
# ==========================================
def get_installation_access_token(jwt_token, org_name):
    """透過 JWT 向 GitHub 換取特定 Org 的 Short-lived Installation Token"""
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # A. 先查詢 App 在該 Org 的 Installation ID
    install_url = f"{GITHUB_API_URL}/orgs/{org_name}/installation"
    response = requests.get(install_url, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Failed to get installation ID: {response.status_code} - {response.text}")

    installation_id = response.json()["id"]

    # B. 取得 Access Token
    token_url = f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens"
    token_response = requests.post(token_url, headers=headers)

    if token_response.status_code != 201:
        raise Exception(f"Failed to create access token: {token_response.status_code} - {token_response.text}")

    return token_response.json()["token"]


# ==========================================
# 4. 業務函數：建立 Repository (可支援使用 Template)
# ==========================================
def create_organization_repository(
    token, 
    org_name, 
    repo_name, 
    description, 
    private=True, 
    template_owner=None, 
    template_repo=None
):
    """
    建立 Repository。
    若傳入 template_owner 與 template_repo，則使用 Template 生成。
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if template_owner and template_repo:
        # 方式 A：從 Template 複製建立 (企業 Best Practice)
        url = f"{GITHUB_API_URL}/repos/{template_owner}/{template_repo}/generate"
        payload = {
            "owner": org_name,
            "name": repo_name,
            "description": description,
            "private": private,
            "include_all_branches": False  # 只複製預設分支
        }
    else:
        # 方式 B：建立空白 Repository
        url = f"{GITHUB_API_URL}/orgs/{org_name}/repos"
        payload = {
            "name": repo_name,
            "description": description,
            "private": private,
            "auto_init": True,  # 自動建立 README.md 產生初始 Commit
            "has_issues": True,
            "has_projects": False,
            "has_wiki": False
        }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code in [201, 202]:
        repo_data = response.json()
        print(f"✅ Repository successfully created: {repo_data['html_url']}")
        return repo_data
    else:
        print(f"❌ Failed to create repository: {response.status_code}")
        print(response.text)
        return None


# ==========================================
# 5. 主程式執行範例
# ==========================================
if __name__ == "__main__":
    try:
        print("1. 正在簽署 JWT...")
        jwt_token = generate_jwt(APP_ID, PRIVATE_KEY_PATH)

        print("2. 正在取得 Installation Access Token...")
        installation_token = get_installation_access_token(jwt_token, ORGANIZATION_NAME)

        # 欲建立的新 Repository 資訊
        NEW_REPO_NAME = "service-payment-api"
        REPO_DESC = "Payment microservice auto-provisioned via Self-Service Portal"

        print(f"3. 開始在 Org [{ORGANIZATION_NAME}] 建立 Repository [{NEW_REPO_NAME}]...")
        
        # 範例：從組織內的微服務範本 (microservice-template) 複製建立
        new_repo = create_organization_repository(
            token=installation_token,
            org_name=ORGANIZATION_NAME,
            repo_name=NEW_REPO_NAME,
            description=REPO_DESC,
            private=True,
            # template_owner=ORGANIZATION_NAME, # 若不使用範本，將這兩行註解即可
            # template_repo="microservice-template"
        )

        if new_repo:
            print(f"🎉 自動建庫完成！Repo ID: {new_repo['id']}")

    except Exception as e:
        print(f"🚨 發生錯誤: {e}")