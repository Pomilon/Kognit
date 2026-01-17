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
                repo_name = item.select_one("span.repo").get_text(strip=True)
                desc = self._get_text(item, "p", "pinned-item-desc") or ""
                lang = self._get_text(item, "span", "itemprop='programmingLanguage'") or "Unknown"
                
                star_a = item.select_one("a[href$='/stargazers']")
                stars = self._parse_count(star_a.get_text(strip=True)) if star_a else 0
                
                node = {
                    "name": repo_name,
                    "description": desc,
                    "url": f"https://github.com/{username}/{repo_name}",
                    "stargazerCount": stars,
                    "primaryLanguage": {"name": lang},
                    "languages": {"nodes": [{"name": lang}]}
                }
                pinned_nodes.append(node)
                pinned_fetch_tasks.append(self._fetch_raw_readme_async(client, username, repo_name))

            # Fetch Pinned READMEs
            pinned_readmes = await asyncio.gather(*pinned_fetch_tasks)
            for node, readme in zip(pinned_nodes, pinned_readmes):
                node["readme"] = {"text": readme} if readme else None
            
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

            repo_fetch_tasks = []
            repo_metadata = []

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
                repo_fetch_tasks.append(self._fetch_raw_readme_async(client, username, r_name))

            # Fetch ALL READMEs concurrently
            print(f"  > Fetching READMEs for {len(repo_metadata)} repositories...")
            all_readmes = await asyncio.gather(*repo_fetch_tasks)
            
            for meta, readme in zip(repo_metadata, all_readmes):
                meta["readme"] = {"text": readme} if readme else None
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

    async def _fetch_raw_readme_async(self, client: httpx.AsyncClient, user: str, repo: str) -> Optional[str]:
        branches = ["main", "master"]
        for branch in branches:
            url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/README.md"
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.text
            except:
                continue
        return None

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
