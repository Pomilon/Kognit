import os
import httpx
import asyncio
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
import re

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

# Increased limit to 100 for Deep Dive
FULL_PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    login
    bio
    websiteUrl
    location
    company
    twitterUsername
    avatarUrl
    
    followers {
      totalCount
    }
    following {
      totalCount
    }
    
    pinnedItems(first: 6, types: [REPOSITORY, GIST]) {
      nodes {
        ... on Repository {
          name
          description
          url
          stargazerCount
          primaryLanguage {
            name
          }
          languages(first: 5) {
            nodes {
              name
            }
          }
          readme: object(expression: "HEAD:README.md") {
            ... on Blob {
              text
            }
          }
          defaultBranchRef {
            target {
              ... on Commit {
                history(first: 4) {
                  totalCount
                  nodes {
                    message
                  }
                }
              }
            }
          }
          tree: object(expression: "HEAD:") {
            ... on Tree {
              entries {
                name
                type
              }
            }
          }
        }
        ... on Gist {
          name
          description
          url
        }
      }
    }
    
    repositories(first: 100, orderBy: {field: STARGAZERS, direction: DESC}, isFork: false) {
      nodes {
        name
        description
        url
        stargazerCount
        isFork
        pushedAt
        primaryLanguage {
          name
        }
        languages(first: 5) {
          nodes {
            name
          }
        }
        repositoryTopics(first: 5) {
          nodes {
            topic {
              name
            }
          }
        }
        readme: object(expression: "HEAD:README.md") {
          ... on Blob {
            text
          }
        }
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 4) {
                totalCount
                nodes {
                  message
                }
              }
            }
          }
        }
        tree: object(expression: "HEAD:") {
          ... on Tree {
            entries {
              name
              type
            }
          }
        }
      }
    }
    
    starredRepositories(first: 20, orderBy: {field: STARRED_AT, direction: DESC}) {
      nodes {
        nameWithOwner
        description
        url
      }
    }
    
    contributionsCollection {
      contributionCalendar {
        totalContributions
      }
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoryContributions
    }
  }
}
"""

class GithubProbe:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if self.token:
            self.auth_headers = {
                **self.headers,
                "Authorization": f"Bearer {self.token}"
            }
        else:
            self.auth_headers = self.headers

    def fetch_profile(self, username: str, use_browser_scraping: bool = False) -> Dict[str, Any]:
        if self.token and not use_browser_scraping:
            try:
                print("  > Attempting Authenticated GraphQL Query (Deep Dive)...")
                return self._fetch_via_api(username)
            except Exception as e:
                print(f"  > API failed ({e}). Falling back to Browser Scraping...")
                return asyncio.run(self._scrape_via_html(username))
        else:
            print("  > Using Browser Scraping Mode (Deep Dive)...")
            return asyncio.run(self._scrape_via_html(username))

    def _fetch_via_api(self, username: str) -> Dict[str, Any]:
        async def _run():
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    GITHUB_GRAPHQL_URL,
                    json={"query": FULL_PROFILE_QUERY, "variables": {"login": username}},
                    headers=self.auth_headers,
                    timeout=15.0
                )
                if response.status_code != 200:
                    raise Exception(f"GitHub API Error: {response.status_code} - {response.text}")
                
                data = response.json()
                if "errors" in data:
                    raise Exception(f"GraphQL Error: {data['errors']}")
                
                return data

        return asyncio.run(_run())

    async def _scrape_via_html(self, username: str) -> Dict[str, Any]:
        """
        Deep scraping of the public HTML profile page + multiple repository pages + stars.
        """
        base_url = f"https://github.com/{username}"
        
        async with httpx.AsyncClient(headers=self.headers, follow_redirects=True) as client:
            # 1. Fetch Main Profile and Tabs
            tasks = [
                client.get(base_url),
                client.get(f"{base_url}?tab=stars")
            ]
            resp_main, resp_stars = await asyncio.gather(*tasks)
            
            if resp_main.status_code == 404:
                raise Exception("User not found")
            
            soup_main = BeautifulSoup(resp_main.text, "html.parser")
            soup_stars = BeautifulSoup(resp_stars.text, "html.parser")

            # --- Identity & Metadata ---
            user_data = {}
            name_tag = soup_main.find("span", class_="p-name")
            user_data["name"] = name_tag.get_text(strip=True) if name_tag else username
            user_data["login"] = username
            
            bio_tag = soup_main.find("div", class_="user-profile-bio")
            user_data["bio"] = bio_tag.get_text(strip=True) if bio_tag else ""
            
            # Avatar
            avatar_img = soup_main.find("img", class_="avatar")
            if avatar_img:
                user_data["avatarUrl"] = avatar_img['src']
            else:
                og_image = soup_main.find("meta", property="og:image")
                user_data["avatarUrl"] = og_image["content"] if og_image else None

            user_data["company"] = self._get_text(soup_main, "span", "p-org")
            user_data["location"] = self._get_text(soup_main, "span", "p-label")
            user_data["websiteUrl"] = self._get_href(soup_main, "a", "u-url")
            user_data["twitterUsername"] = self._get_href(soup_main, "a", "Link--primary")
            
            # Counts
            followers_a = soup_main.select_one(f"a[href*='tab=followers'] span.text-bold")
            user_data["followers"] = {"totalCount": self._parse_count(followers_a.get_text(strip=True)) if followers_a else 0}
            
            following_a = soup_main.select_one(f"a[href*='tab=following'] span.text-bold")
            user_data["following"] = {"totalCount": self._parse_count(following_a.get_text(strip=True)) if following_a else 0}

            # Contributions
            contrib_h2 = soup_main.find("h2", class_="f4 text-normal mb-2")
            total_contribs = 0
            
            if not contrib_h2:
                # GitHub often loads contributions via include-fragment
                fragment = soup_main.find("include-fragment", src=re.compile(r"tab=contributions"))
                if fragment:
                    fragment_url = f"https://github.com{fragment['src']}"
                    try:
                        resp_frag = await client.get(
                            fragment_url, 
                            headers={**self.headers, "X-Requested-With": "XMLHttpRequest"}
                        )
                        if resp_frag.status_code == 200:
                            soup_frag = BeautifulSoup(resp_frag.text, "html.parser")
                            # The h2 in the fragment might have slightly different classes
                            contrib_h2 = soup_frag.find("h2", class_=re.compile(r"f4 text-normal"))
                    except Exception as e:
                        print(f"  > Warning: Failed to fetch contribution fragment: {e}")

            if contrib_h2:
                match = re.search(r"([\d,]+)\s+contributions", contrib_h2.get_text())
                if match:
                    total_contribs = int(match.group(1).replace(",", ""))
            
            user_data["contributionsCollection"] = {"contributionCalendar": {"totalContributions": total_contribs}}

            # --- Pinned Items ---
            pinned_nodes = []
            pinned_list = soup_main.select("ol.js-pinned-items-reorder-list li")
            pinned_fetch_tasks = []

            for item in pinned_list:
                repo_link_el = item.select_one("a[data-hydro-click*='PINNED_REPO']")
                if not repo_link_el:
                    repo_link_el = item.select_one("a")
                
                repo_path = repo_link_el.get("href", "") if repo_link_el else ""
                repo_name = item.select_one("span.repo").get_text(strip=True)
                desc = self._get_text(item, "p", "pinned-item-desc") or ""
                lang = self._get_text(item, "span", "itemprop='programmingLanguage'") or "Unknown"
                
                star_a = item.select_one("a[href$='/stargazers']")
                stars = self._parse_count(star_a.get_text(strip=True)) if star_a else 0
                
                full_url = f"https://github.com{repo_path}"
                node = {
                    "name": repo_name,
                    "description": desc,
                    "url": full_url,
                    "stargazerCount": stars,
                    "primaryLanguage": {"name": lang},
                    "languages": {"nodes": [{"name": lang}]}
                }
                pinned_nodes.append(node)
                # Fetch Structure & README concurrently
                pinned_fetch_tasks.append(self._fetch_repo_details_async(client, full_url))

            # Fetch Pinned Details
            pinned_details = await asyncio.gather(*pinned_fetch_tasks)
            for node, details in zip(pinned_nodes, pinned_details):
                node["readme"] = {"text": details["readme"]} if details["readme"] else None
                node["tree"] = {"entries": details["tree"]}
                node["defaultBranchRef"] = {
                    "target": {
                        "history": {
                            "totalCount": details["commits"],
                            "nodes": [{"message": m} for m in details["latest_commits"]]
                        }
                    }
                }
            
            user_data["pinnedItems"] = {"nodes": pinned_nodes}

            # --- Repositories (Pagination) ---
            print("  > Scraping Repositories (Pages 1-3)...")
            repo_nodes = []
            
            # Fetch up to 3 pages concurrently (approx 90 repos)
            page_tasks = [client.get(f"{base_url}?tab=repositories&page={i}") for i in range(1, 4)]
            page_responses = await asyncio.gather(*page_tasks)
            
            all_repo_items = []
            for resp in page_responses:
                soup_page = BeautifulSoup(resp.text, "html.parser")
                all_repo_items.extend(soup_page.select("li[itemprop='owns']"))

            repo_metadata = []
            repo_fetch_tasks = []

            for item in all_repo_items:
                name_tag = item.select_one("a[itemprop='name codeRepository']")
                if not name_tag: continue
                
                r_name = name_tag.get_text(strip=True)
                r_url = f"https://github.com{name_tag['href']}"
                r_desc = self._get_text(item, "p", "itemprop='description'") or ""
                r_lang = self._get_text(item, "span", "itemprop='programmingLanguage'") or "N/A"
                
                r_star_a = item.select_one("a[href*='stargazers']")
                r_stars = self._parse_count(r_star_a.get_text(strip=True)) if r_star_a else 0
                
                r_time = item.select_one("relative-time")
                r_date = r_time['datetime'] if r_time else "Unknown"

                meta = {
                    "name": r_name,
                    "description": r_desc,
                    "url": r_url,
                    "stargazerCount": r_stars,
                    "isFork": False,
                    "pushedAt": r_date,
                    "primaryLanguage": {"name": r_lang},
                    "languages": {"nodes": [{"name": r_lang}]}
                }
                repo_metadata.append(meta)
                repo_fetch_tasks.append(self._fetch_repo_details_async(client, r_url))

            # Fetch ALL Details concurrently
            print(f"  > Fetching metadata and structure for {len(repo_metadata)} repositories...")
            all_details = await asyncio.gather(*repo_fetch_tasks)
            
            for meta, details in zip(repo_metadata, all_details):
                meta["readme"] = {"text": details["readme"]} if details["readme"] else None
                meta["tree"] = {"entries": details["tree"]}
                meta["defaultBranchRef"] = {
                    "target": {
                        "history": {
                            "totalCount": details["commits"],
                            "nodes": [{"message": m} for m in details["latest_commits"]]
                        }
                    }
                }
                repo_nodes.append(meta)

            user_data["repositories"] = {"nodes": repo_nodes}

            # --- Starred Repos ---
            starred_nodes = []
            star_items = soup_stars.select("div.col-lg-12") # Starred repos usually in a list
            # GitHub stars page structure varies, usually: "div.d-inline-block.mb-1 h3 a"
            
            # Simple fallback scrape for stars (Top 10)
            s_links = soup_stars.select("h3 a")
            for link in s_links[:10]:
                owner_repo = link.get('href', '').strip('/')
                starred_nodes.append({
                    "nameWithOwner": owner_repo,
                    "description": "Scraped via Web",
                    "url": f"https://github.com/{owner_repo}"
                })
            
            user_data["starredRepositories"] = {"nodes": starred_nodes}

            return {"data": {"user": user_data}}

    async def _fetch_repo_details_async(self, client: httpx.AsyncClient, repo_url: str) -> Dict[str, Any]:
        """
        Fetches README, Root structure, latest commits, and total commits for a repo.
        """
        details = {"readme": None, "tree": [], "commits": 0, "latest_commits": []}
        
        try:
            # 1. Fetch Main Page for structure and commit count
            resp = await client.get(repo_url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # --- Commit Count ---
                commit_text = soup.find(lambda tag: tag.name == "span" and "commits" in tag.get_text().lower())
                if commit_text:
                    match = re.search(r"([\d,]+)", commit_text.get_text())
                    if match:
                        details["commits"] = self._parse_count(match.group(1))
                
                if details["commits"] == 0:
                    commit_span = soup.select_one("span.d-none.d-sm-inline strong")
                    if commit_span:
                        details["commits"] = self._parse_count(commit_span.get_text(strip=True))

                # --- Latest Commit Messages ---
                try:
                    commits_url = f"{repo_url}/commits"
                    c_resp = await client.get(commits_url)
                    if c_resp.status_code == 200:
                        c_soup = BeautifulSoup(c_resp.text, "html.parser")
                        msgs = []
                        
                        # Try JSON first (Modern GitHub)
                        c_embedded = c_soup.find("script", {"data-target": "react-app.embeddedData"})
                        if c_embedded:
                            try:
                                c_json = json.loads(c_embedded.get_text())
                                payload = c_json.get("payload") or {}
                                groups = payload.get("commitGroups") or []
                                for group in groups:
                                    if not group: continue
                                    commits = group.get("commits") or []
                                    for c in commits:
                                        if not c: continue
                                        msg = c.get("shortMessage")
                                        if msg and msg not in msgs:
                                            msgs.append(msg)
                                        if len(msgs) >= 4: break
                                    if len(msgs) >= 4: break
                            except:
                                pass
                        
                        # Fallback to selectors if JSON failed or was empty
                        if not msgs:
                            # 1. Modern: data-testid="commit-row-item-message" or similar inside rows
                            # Often rows are <li> or <div>
                            commit_rows = c_soup.select("div[data-testid='commit-row-item'], li.Box-row")
                            for row in commit_rows:
                                msg_link = row.select_one("h4 a, a.Link--primary, .commit-title a")
                                if msg_link:
                                    text = msg_link.get_text(strip=True)
                                    if text and text not in msgs:
                                        msgs.append(text)
                                if len(msgs) >= 4: break
                            
                            # 2. Ultra-fallback: just find any Links that look like commits
                            if not msgs:
                                all_commit_links = c_soup.find_all("a", href=re.compile(r"/commit/[a-f0-9]{40}"))
                                for link in all_commit_links:
                                    text = link.get_text(strip=True)
                                    # Filter out the SHA-only links
                                    if text and len(text) > 8 and text not in msgs:
                                        msgs.append(text)
                                    if len(msgs) >= 4: break
                        
                        if msgs:
                            details["latest_commits"] = msgs
                except:
                    pass

                # --- Tree Structure ---
                links = soup.select("a.Link--primary")
                seen_names = set()
                
                # Extract repo path for child check
                repo_path = "/" + "/".join(repo_url.split("/")[-2:]) # /user/repo
                
                for link in links:
                    href = link.get("href", "")
                    name = link.get_text(strip=True)
                    
                    if not name or name in seen_names:
                        continue
                    
                    if f"{repo_path}/tree/" in href or f"{repo_path}/blob/" in href:
                        parts = href.strip("/").split("/")
                        if len(parts) >= 5:
                            seen_names.add(name)
                            e_type = "tree" if "/tree/" in href else "blob"
                            details["tree"].append({"name": name, "type": e_type})

            # 2. Fetch README (Raw)
            raw_url = repo_url.replace("github.com", "raw.githubusercontent.com")
            branches = ["main", "master"]
            for branch in branches:
                r_resp = await client.get(f"{raw_url}/{branch}/README.md")
                if r_resp.status_code == 200:
                    details["readme"] = r_resp.text
                    break
        except Exception as e:
            print(f"  > Warning: Detail fetch failed for {repo_url}: {e}")
            
        return details

    def _get_text(self, soup, tag, selector_str):
        # Helper that handles class or prop attributes roughly
        if "=" in selector_str:
            attr, val = selector_str.split("=")
            val = val.strip("'\"")
            el = soup.find(tag, attrs={attr: val})
        else:
            el = soup.find(tag, class_=selector_str)
        return el.get_text(strip=True) if el else None

    def _get_href(self, soup, tag, class_name):
        el = soup.find(tag, class_=class_name)
        return el['href'] if el and 'href' in el.attrs else None
    
    def _parse_count(self, text: str) -> int:
        text = text.lower().strip().replace(",", "")
        try:
            if "k" in text:
                return int(float(text.replace("k", "")) * 1000)
            if "m" in text:
                return int(float(text.replace("m", "")) * 1_000_000)
            return int(text)
        except ValueError:
            return 0
