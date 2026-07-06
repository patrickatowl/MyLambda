#!/usr/bin/env python3
import requests
import csv
import sys
import os
import argparse
from collections import defaultdict

GITHUB_TOKEN = None  # Set via command line or environment
ORG_NAME = "OwlTing"
repo_file="./repo_list.txt"


def github_api(endpoint, params=None):
    """Make GitHub API request with pagination support"""
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    url = f"https://api.github.com{endpoint}"
    results = []

    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        results.extend(data if isinstance(data, list) else [data])
        url = response.links.get('next', {}).get('url')
        params = None  # Params only for first request

    return results

def load_repo_list(filepath):
    """Load repo names from a text file, one per line"""
    if not os.path.isabs(filepath):
        filepath = os.path.join(os.path.dirname(__file__), filepath)
    with open(filepath, encoding='utf-8') as f:
        repos = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    print(f"Loaded {len(repos)} repos from {filepath}", file=sys.stderr)
    return repos



def get_org_repos():
    """Get all repositories in the organization via API"""
    repos = github_api(f"/orgs/{ORG_NAME}/repos", {"per_page": 100})
    return sorted(repo['name'] for repo in repos)

def get_org_members():
    """Get all members in the organization (internal + outside collaborators)"""
    members = github_api(f"/orgs/{ORG_NAME}/members", {"per_page": 100})
    logins = set(member['login'] for member in members)

    outside = github_api(f"/orgs/{ORG_NAME}/outside_collaborators", {"per_page": 100})
    logins.update(member['login'] for member in outside)

    return sorted(logins)

def get_repo_collaborators(repo_name):
    """Get all collaborators for a repository (direct + outside)"""
    try:
        collabs = github_api(f"/repos/{ORG_NAME}/{repo_name}/collaborators", {"per_page": 100, "affiliation": "all"})
        return {collab['login']: collab['permissions'] for collab in collabs}
    except requests.HTTPError as e:
        print(f"Warning: could not fetch collaborators for {repo_name}: {e}", file=sys.stderr)
        return {}

def get_repo_teams(repo_name):
    """Get teams with access to a repository"""
    try:
        teams = github_api(f"/repos/{ORG_NAME}/{repo_name}/teams", {"per_page": 100})
        return {team['slug']: team['permission'] for team in teams}
    except requests.HTTPError as e:
        print(f"Warning: could not fetch teams for {repo_name}: {e}", file=sys.stderr)
        return {}

def get_team_members(team_slug):
    """Get members of a team"""
    try:
        members = github_api(f"/orgs/{ORG_NAME}/teams/{team_slug}/members", {"per_page": 100})
        return [member['login'] for member in members]
    except requests.HTTPError as e:
        print(f"Warning: could not fetch members for team {team_slug}: {e}", file=sys.stderr)
        return []

def permission_priority(perm_dict):
    """Convert permission dict to single permission string with priority"""
    if perm_dict.get('admin'):
        return 'admin'
    if perm_dict.get('maintain'):
        return 'maintain'
    if perm_dict.get('push'):
        return 'write'
    if perm_dict.get('triage'):
        return 'triage'
    if perm_dict.get('pull'):
        return 'read'
    return 'none'

def permission_mapping(perm_list):
    """Convert permission list to single permission string with priority"""
    if 'admin' in perm_list:
        return 'admin'
    if 'maintain' in perm_list:
        return 'maintain'
    if 'push' in perm_list:
        return 'write'
    if 'triage' in perm_list:
        return 'triage'
    if 'pull' in perm_list:
        return 'read'
    return 'none'

def get_user_permissions(repos=None):
    """Build matrix of user permissions across all repos"""
    if repos is None:
        repos = get_org_repos()
    members = get_org_members()
    
    # Initialize permissions matrix
    permissions = {member: {} for member in members}
 
    for repo in repos:
        print(f"Processing {repo}...", file=sys.stderr)
        
        # Get direct collaborators
        collaborators = get_repo_collaborators(repo)
        
        # Get teams and their members
        teams = get_repo_teams(repo)
        team_permissions = defaultdict(list)
        
        for team_slug, team_perm in teams.items():
            team_members = get_team_members(team_slug)
            for member in team_members:
                team_permissions[member].append(team_perm)

        # Assign permissions to each member
        for member in members:
            perms = []
            
            # Direct collaborator permission
            if member in collaborators:
                perms.append(permission_priority(collaborators[member]))
            
            # Team permissions
            if member in team_permissions:
                perms.append(permission_mapping(team_permissions[member]))
            
            # Determine highest permission
            if perms:
                perm_order = ['admin', 'maintain', 'write', 'triage', 'read']
                for p in perm_order:
                    if p in perms:
                        permissions[member][repo] = p
                        break
            else:
                permissions[member][repo] = ''
    
    return permissions, repos, members


def get_unique_filename(filepath):
    """如果檔案存在，自動在檔名後加上 _1, _2 等序號"""
    if not os.path.exists(filepath):
        return filepath
    
    # 拆分路徑、檔名與副檔名 (例如: 'output/permissions.csv' -> 'output/permissions', '.csv')
    base, ext = os.path.splitext(filepath)
    counter = 1
    
    # 循環檢查，直到找到不存在的檔名
    while os.path.exists(f"{base}_{counter}{ext}"):
        counter += 1
        
    return f"{base}_{counter}{ext}"


def write_csv(permissions, repos, members, output_file='permissions.csv'):
    """Write permissions matrix to CSV"""
    # ➡️ 1. 指定輸出的資料夾名稱
    target_dir = 'output'    
    # ➡️ 2. 如果資料夾不存在，就自動建立它 (exist_ok=True 代表如果已存在也不會報錯)
    os.makedirs(target_dir, exist_ok=True)    
    # ➡️ 3. 取得原本的檔名（例如從 'path/to/permissions.csv' 取出 'permissions.csv'）
    filename = os.path.basename(output_file)    
    # ➡️ 4. 組合新的路徑成 'output/permissions.csv'
    new_filepath = os.path.join(target_dir, filename)
    output_file = get_unique_filename(new_filepath)
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Header row
        writer.writerow([''] + repos)
        
        # User rows
        for member in members:
            row = [member] + [permissions[member].get(repo, '') for repo in repos]
            writer.writerow(row)
    
    print(f"CSV written to {output_file}", file=sys.stderr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('token', help='GitHub personal access token')
    parser.add_argument('--repo-list', default='repo_list.txt', help='Path to repo list file (one repo per line)')
    parser.add_argument('--org', default='OwlTing', help='GitHub organization name')
    parser.add_argument('--output', default='permissions.csv', help='Output CSV path')
    parser.add_argument('--all-repos', action='store_true', help='Ignore repo-list and fetch all repos from org API')
    args = parser.parse_args()

    GITHUB_TOKEN = args.token
    ORG_NAME = args.org

    if args.all_repos:
        repos = get_org_repos()
    else:
        repos = load_repo_list(args.repo_list)

    permissions, repos, members = get_user_permissions(repos)
    write_csv(permissions, repos, members, args.output)
