from typing import Dict, Any, List

def normalize_profile_context(
    github_data: Dict[str, Any], 
    external_content: Dict[str, str],
    search_results: List[Dict[str, str]] = [],
    include_readmes: bool = True
) -> str:
    """
    Combines GitHub data, external web content, and search results into a single context string.
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
    lines.append(f"Total Contributions (Year): {user.get('contributionsCollection', {}).get('contributionCalendar', {}).get('totalContributions')}")
    lines.append("")
    
    # Search Context
    if search_results:
        lines.append("## Web Search Context (Online Presence)")
        for res in search_results:
            lines.append(f"- [{res.get('title')}]({res.get('href')})")
            lines.append(f"  Snippet: {res.get('body')}")
        lines.append("")

    # Pinned Items
    lines.append("## Pinned Projects (High Signal)")
    pinned = user.get("pinnedItems", {}).get("nodes", [])
    for item in pinned:
        lines.append(f"### {item.get('name')}")
        lines.append(f"Description: {item.get('description')}")
        lines.append(f"URL: {item.get('url')}")
        if 'stargazerCount' in item:
            lines.append(f"Stars: {item.get('stargazerCount')}")
        if 'primaryLanguage' in item and item['primaryLanguage']:
            lines.append(f"Language: {item['primaryLanguage']['name']}")
        
        # README Content (Truncated)
        readme = item.get("readme")
        if include_readmes and readme and isinstance(readme, dict) and readme.get("text"):
            lines.append("README Snippet:")
            lines.append(f"```\n{readme.get('text')[:3000]}\n```") 
            
        lines.append("")

    # Recent/Top Repos
    lines.append("## Top Repositories (Active & Significant)")
    lines.append("Note: These repositories are statistically significant. Analyze them for technical depth even if not pinned.")
    repos = user.get("repositories", {}).get("nodes", [])
    
    # Limit detailed context to top 15 repos to avoid context flooding
    for i, repo in enumerate(repos):
        lines.append(f"- **{repo.get('name')}**: {repo.get('description')}")
        langs = [l['name'] for l in repo.get('languages', {}).get('nodes', [])]
        lines.append(f"  Stack: {', '.join(langs)}")
        lines.append(f"  Stars: {repo.get('stargazerCount')} | Updated: {repo.get('pushedAt')}")
        
        # README Snippet for top repos (Limited to first 10 for deep context)
        if include_readmes and i < 15:
            readme = repo.get("readme")
            if readme and isinstance(readme, dict) and readme.get("text"):
                 lines.append(f"  README Extract: {readme.get('text')[:1000]}...")
             
    lines.append("")

    # External Content
    if external_content:
        lines.append("## External Web Content (Blogs/Portfolios)")
        for url, content in external_content.items():
            lines.append(f"### Source: {url}")
            lines.append(f"```markdown\n{content[:2000]}\n```\n... (content truncated)\n")

    return "\n".join(lines)
