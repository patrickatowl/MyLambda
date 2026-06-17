#!/usr/bin/env python3
import requests
import csv
import sys
from collections import defaultdict

GITHUB_TOKEN = None  # Set via command line or environment
ORG_NAME = "OwlTing"
REPO_FILTER = []  # Optional: list of repo names to include

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

def get_org_repos():
    """Get all repositories in the organization"""
    repos = github_api(f"/orgs/{ORG_NAME}/repos", {"per_page": 100})
    repo_names = [repo['name'] for repo in repos]
    
    if REPO_FILTER:
        repo_names = [name for name in repo_names if name in REPO_FILTER]
    
    return sorted(repo_names)

def get_org_members():
    """Get all members in the organization"""
    members = github_api(f"/orgs/{ORG_NAME}/members", {"per_page": 100})
    return sorted([member['login'] for member in members])

def get_repo_collaborators(repo_name):
    """Get direct collaborators for a repository"""
    try:
        collabs = github_api(f"/repos/{ORG_NAME}/{repo_name}/collaborators", {"per_page": 100, "affiliation": "direct"})
        return {collab['login']: collab['permissions'] for collab in collabs}
    except:
        return {}

def get_repo_teams(repo_name):
    """Get teams with access to a repository"""
    try:
        teams = github_api(f"/repos/{ORG_NAME}/{repo_name}/teams", {"per_page": 100})
        return {team['slug']: team['permission'] for team in teams}
    except:
        return {}

def get_team_members(team_slug):
    """Get members of a team"""
    try:
        members = github_api(f"/orgs/{ORG_NAME}/teams/{team_slug}/members", {"per_page": 100})
        return [member['login'] for member in members]
    except:
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

def get_user_permissions():
    """Build matrix of user permissions across all repos"""
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

def write_csv(permissions, repos, members, output_file='permissions.csv'):
    """Write permissions matrix to CSV"""
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
    if len(sys.argv) < 2:
        print("Usage: python github_user_inventory.py <GITHUB_TOKEN> [output.csv]")
        sys.exit(1)
    
    GITHUB_TOKEN = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'permissions.csv'
    
    permissions, repos, members = get_user_permissions()
    write_csv(permissions, repos, members, output_file)
