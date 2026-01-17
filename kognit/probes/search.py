from duckduckgo_search import DDGS
from typing import List, Dict, Optional

class SearchProbe:
    def __init__(self):
        self.ddgs = DDGS()

    def search_developer(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Searches for the developer online to find external footprint.
        """
        results = []
        try:
            # We add keywords to focus on technical content
            refined_query = f"{query} software developer github engineering"
            print(f"  > Probing Web: '{refined_query}'")
            
            ddg_results = self.ddgs.text(refined_query, max_results=max_results)
            if ddg_results:
                for r in ddg_results:
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", "")
                    })
        except Exception as e:
            print(f"  [SearchProbe] Error: {e}")
        
        return results
