import pytest
from kognit.probes.normalizer import normalize_profile_context
from kognit.refinery.validator import validate_links
from kognit.models.identity import DeveloperIdentity, TechnicalDNA, ExternalFootprint

def test_normalizer_structure():
    mock_github = {
        "data": {
            "user": {
                "name": "Test User",
                "login": "testuser",
                "bio": "Test bio",
                "repositories": {"nodes": []},
                "pinnedItems": {"nodes": []},
                "followers": {"totalCount": 0},
                "contributionsCollection": {"contributionCalendar": {"totalContributions": 0}}
            }
        }
    }
    context = normalize_profile_context(mock_github, include_readmes=True)
    assert "Test User" in context
    assert "## Identity" in context

def test_validator_reachability():
    identity = DeveloperIdentity(
        name="Test", headline="Test", summary="Test",
        technical_dna=TechnicalDNA(specialization="Test"),
        external_footprint=ExternalFootprint(writing_style="Test"),
        external_links=["https://github.com", "https://invalid-link-12345.com"]
    )
    invalid = validate_links(identity, "")
    assert "https://invalid-link-12345.com" in invalid
    assert "https://github.com" not in invalid

if __name__ == "__main__":
    # Manual run if needed
    test_normalizer_structure()
    print("Tests passed!")
