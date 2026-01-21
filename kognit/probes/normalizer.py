from typing import Dict, Any, List

def normalize_profile_context(
    github_data: Dict[str, Any], 
    include_readmes: bool = True,
    max_readme_chars: int = 3000,
    max_repos: int = 15
) -> str:
    """
    Transforms GitHub GraphQL data into a dense, searchable Markdown context.
    """
    lines = ["# Developer Digital Footprint\n"]
    
    user = github_data.get("data", {}).get("user", {})
    if not user:
        return "No user data found."

    # Identity
    lines.append(f"## Identity")
    lines.append(f"Name: {user.get('name')}")
    lines.append(f"Handle: {user.get('login')}")
    lines.append(f"Avatar: {user.get('avatarUrl')}")
    lines.append(f"Bio: {user.get('bio')}")
    lines.append(f"Company: {user.get('company')}")
    lines.append(f"Location: {user.get('location')}")
    lines.append(f"Website: {user.get('websiteUrl')}")
    lines.append(f"Twitter: {user.get('twitterUsername')}")
    lines.append(f"Followers: {user.get('followers', {}).get('totalCount')}")
    contribs = user.get('contributionsCollection', {})
    calendar = contribs.get('contributionCalendar', {})
    lines.append(f"Total Contributions (Year): {calendar.get('totalContributions')}")
    if contribs.get('totalCommitContributions'):
        lines.append(f" - Commits: {contribs.get('totalCommitContributions')}")
        lines.append(f" - Pull Requests: {contribs.get('totalPullRequestContributions')}")
        lines.append(f" - Issues: {contribs.get('totalIssueContributions')}")
        lines.append(f" - Repos Created: {contribs.get('totalRepositoryContributions')}")
    lines.append("")
    
    # Pinned Items
    lines.append("## Pinned Projects (High Signal)")
    pinned = (user.get("pinnedItems") or {}).get("nodes") or []
    for item in pinned:
        if not item: continue
        lines.append(f"### {item.get('name')}")
        lines.append(f"Description: {item.get('description')}")
        lines.append(f"URL: {item.get('url')}")
        if 'stargazerCount' in item:
            lines.append(f"Stars: {item.get('stargazerCount')}")
        if item.get('primaryLanguage'):
            lines.append(f"Language: {item['primaryLanguage']['name']}")
        
        # Structure & Stats
        history = item.get("defaultBranchRef") or {}
        if history: history = history.get("target") or {}
        if history: history = history.get("history") or {}
        
        commits = history.get("totalCount", 0)
        lines.append(f"Total Commits: {commits}")
        
        nodes = history.get("nodes") or []
        if nodes:
            lines.append("Latest Commits:")
            for node in nodes:
                if node and node.get("message"):
                    lines.append(f" - {node['message']}")
        
        tree = (item.get("tree") or {}).get("entries") or []
        if tree:
            struct = [f"{e['name']}{'/' if e['type'] == 'tree' else ''}" for e in tree if e]
            lines.append(f"Repo Structure (Root): {', '.join(struct)}")

        # README Content (Truncated)
        readme = item.get("readme")
        if include_readmes and readme and isinstance(readme, dict) and readme.get("text"):
            lines.append("README Snippet:")
            lines.append(f"```\n{readme.get('text')[:max_readme_chars]}\n```") 
            
        lines.append("")

    # Recent/Top Repos
    lines.append("## Top Repositories (Active & Significant)")
    lines.append("Note: These repositories are statistically significant. Analyze them for technical depth even if not pinned.")
    repos = (user.get("repositories") or {}).get("nodes") or []
    
    # Limit detailed context to avoid context flooding
    for i, repo in enumerate(repos[:max_repos]):
        if not repo: continue
        lines.append(f"- **{repo.get('name')}**: {repo.get('description')}")
        langs_nodes = (repo.get('languages') or {}).get('nodes') or []
        langs = [l['name'] for l in langs_nodes if l and 'name' in l]
        lines.append(f"  Stack: {', '.join(langs)}")
        lines.append(f"  Stars: {repo.get('stargazerCount')} | Updated: {repo.get('pushedAt')}")
        
        history = repo.get("defaultBranchRef") or {}
        if history: history = history.get("target") or {}
        if history: history = history.get("history") or {}
        
        commits = history.get("totalCount", 0)
        lines.append(f"  Total Commits: {commits}")
        
        nodes = history.get("nodes") or []
        if nodes:
            lines.append("  Latest Commits:")
            for node in nodes:
                if node and node.get("message"):
                    lines.append(f"   - {node['message']}")
        
        tree = (repo.get("tree") or {}).get("entries") or []
        if tree:
            struct = [f"{e['name']}{'/' if e['type'] == 'tree' else ''}" for e in tree if e]
            lines.append(f"  Structure: {', '.join(struct)}")

        # README Snippet for top repos (Smaller than pinned)
        if include_readmes:
            readme = repo.get("readme")
            if readme and isinstance(readme, dict) and readme.get("text"):
                 # Use a smaller fraction of the max limit for unpinned repos
                 limit = max(500, max_readme_chars // 3)
                 lines.append(f"  README Extract: {readme.get('text')[:limit]}...")
             
    lines.append("")

    return "\n".join(lines)