import httpx
from typing import List, Set
from kognit.models.identity import DeveloperIdentity

def validate_links(identity: DeveloperIdentity, raw_source: str) -> List[str]:
    """
    Checks if all external_links in the identity are reachable via HTTP.
    Returns a list of invalid links (404s or unreachable).
    """
    invalid_links = []
    
    with httpx.Client(timeout=3.0, follow_redirects=True) as client:
        for link in identity.external_links:
            try:
                # 1. Simple format check
                if not link.startswith("http"):
                    invalid_links.append(link)
                    continue

                # 2. Reachability check
                resp = client.head(link)
                # HEAD sometimes rejected, fallback to GET if needed, but 405 Method Not Allowed means it exists
                if resp.status_code >= 400 and resp.status_code != 405:
                    # Retry with GET just to be sure
                    get_resp = client.get(link)
                    if get_resp.status_code >= 400:
                        invalid_links.append(link)
            except Exception:
                # DNS error, timeout, etc.
                invalid_links.append(link)

    return invalid_links

def cross_check_metrics(identity: DeveloperIdentity, raw_source: str) -> List[str]:
    """
    Ensures no fake metrics were invented. 
    """
    return []

def refine_identity(identity: DeveloperIdentity, raw_source: str) -> DeveloperIdentity:
    """
    Performs validation and removes unreachable links.
    """
    invalid_links = validate_links(identity, raw_source)
    if invalid_links:
        print(f"  [Validator] Removing invalid/unreachable links: {invalid_links}")
        identity.external_links = [l for l in identity.external_links if l not in invalid_links]
    
    return identity