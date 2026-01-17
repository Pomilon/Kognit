import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from typing import Optional

class WebProbe:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Kognit/1.0; +https://github.com/pomilon/kognit)"
        }

    def scrape_page(self, url: str) -> Optional[str]:
        """
        Fetches a URL and converts its main content to Markdown.
        """
        try:
            with httpx.Client(headers=self.headers, follow_redirects=True, timeout=10.0) as client:
                response = client.get(url)
                response.raise_for_status()
                
                # Basic cleaning
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Remove script/style elements
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                # Convert to Markdown
                text = md(str(soup))
                
                # Limit length to avoid context overflow
                return text[:8000] 
                
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return None
