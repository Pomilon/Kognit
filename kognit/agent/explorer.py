from typing import List, Dict, Any
import asyncio
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from kognit.probes.github import GithubProbe
from kognit.models.identity import ProjectHighlight
from kognit.models.analysis import RepoAnalysis

REPO_ANALYST_PROMPT = """
You are a Senior Code Auditor. Your task is to analyze a single repository based on its README and metadata.

**CRITICAL:** You MUST output your analysis by calling the provided tool/function. Do NOT output plain text.
Fill the fields:
- `technical_deconstruction`: Your full markdown analysis.
- `complexity_score`: Integer 1-10.
- `key_technologies`: List of strings.
"""

class ExplorerAgent:
    def __init__(self, model_name: str = 'google-gla:gemini-flash-latest', humor: int = 0, is_roast: bool = False):
        self.model_name = model_name
        
        # Dynamic Prompt Construction
        prompt = REPO_ANALYST_PROMPT
        
        if is_roast:
            prompt += """
            **TONE: ROAST MODE 🔥**
            You are a ruthless, cynical senior engineer. Tear this code apart.
            - Mock bad patterns, over-engineering, or lack of tests.
            - If the code is actually good, begrudgingly admit it but find something nitpicky.
            - Be savage but technically accurate.
            """
        elif humor > 0:
            prompt += f"""
            **TONE: Humorous (Level {humor}/100)**
            Inject wit, sarcasm, and technical jokes into your analysis.
            Level 100 means full-blown stand-up comedy style.
            Current Level: {humor}. Adjust your sarcasm accordingly.
            """
            
        self.analyst_agent = Agent(
            model_name,
            output_type=RepoAnalysis,
            system_prompt=prompt
        )

    async def analyze_repository(self, repo_data: Dict[str, Any]) -> RepoAnalysis:
        """
        Analyzes a single repository in isolation.
        """
        readme_text = ""
        if repo_data.get("readme"):
            readme_text = repo_data["readme"].get("text", "")[:8000] # Generous limit for single repo

        context = f"""
        Repository: {repo_data.get('name')}
        Description: {repo_data.get('description')}
        Languages: {', '.join([n['name'] for n in repo_data.get('languages', {}).get('nodes', [])])}
        Stars: {repo_data.get('stargazerCount')}
        
        README Content:
        {readme_text}
        """
        
        try:
            result = await self.analyst_agent.run(context)
            return result.output
        except Exception as e:
            # Attempt to recover content from failed_generation if model refused tool use
            # This is common with some models that prefer chatting over function calling
            error_str = str(e)
            content = "Analysis failed."
            
            # Check for failed_generation in the error body (PydanticAI/Groq specific)
            try:
                if hasattr(e, 'body') and isinstance(e.body, dict):
                    failed_gen = e.body.get('error', {}).get('failed_generation')
                    if failed_gen:
                        content = failed_gen
                elif "'failed_generation':" in error_str:
                    # Fallback string parsing if object access fails
                    import re
                    match = re.search(r"'failed_generation':\s*(?:\"|')(.+?)(?:\"|')\}", error_str, re.DOTALL)
                    if match:
                        content = match.group(1).encode('utf-8').decode('unicode_escape') # Unescape newlines
            except:
                pass

            if content != "Analysis failed.":
                # We successfully recovered the text!
                return RepoAnalysis(
                    name=repo_data.get('name', 'Unknown'),
                    summary="Recovered from raw model output.",
                    technical_deconstruction=content,
                    key_technologies=["Inferred"],
                    complexity_score=5 # Default
                )

            # Fallback for empty/failed analysis
            return RepoAnalysis(
                name=repo_data.get('name', 'Unknown'),
                summary="Analysis failed or skipped.",
                technical_deconstruction=f"Could not analyze deeply. Error: {str(e)[:500]}...",
                key_technologies=[],
                complexity_score=0
            )

    async def full_dive(self, user_data: Dict[str, Any], max_repos: int = 20) -> Dict[str, Any]:
        """
        Orchestrates the full dive: serial/parallel analysis of all repos.
        """
        repos = user_data.get("repositories", {}).get("nodes", [])
        # Prioritize: Pinned first, then by stars
        # (Assuming the probe already sorted them or we can sort here)
        
        # We limit to max_repos to avoid infinite loops, but "full dive" implies high coverage.
        target_repos = repos[:max_repos]
        
        print(f"  [Explorer] Starting deep analysis of {len(target_repos)} repositories...")
        
        analyses = []
        # Run sequentially or chunks to avoid rate limits? 
        # Parallel is faster but hits rate limits instantly. 
        # Let's do chunks of 3.
        
        chunk_size = 3
        for i in range(0, len(target_repos), chunk_size):
            chunk = target_repos[i:i+chunk_size]
            tasks = [self.analyze_repository(repo) for repo in chunk]
            results = await asyncio.gather(*tasks)
            analyses.extend(results)
            print(f"  [Explorer] Analyzed {len(analyses)}/{len(target_repos)}...")
            
        return self._compile_report(analyses)

    def _compile_report(self, analyses: List[RepoAnalysis]) -> Dict[str, Any]:
        """
        Compiles individual analyses into a format suitable for the final identity synthesis.
        """
        # Create a massive consolidated report string
        full_report_lines = ["# Full-Dive Technical Audit\n"]
        
        # Sort by complexity
        sorted_analyses = sorted(analyses, key=lambda x: x.complexity_score, reverse=True)
        
        for analysis in sorted_analyses:
            full_report_lines.append(f"## {analysis.name} (Complexity: {analysis.complexity_score}/10)")
            full_report_lines.append(f"**Tech Stack:** {', '.join(analysis.key_technologies)}")
            full_report_lines.append(f"### Deconstruction")
            full_report_lines.append(analysis.technical_deconstruction)
            full_report_lines.append("---\n")
            
        return {
            "consolidated_report": "\n".join(full_report_lines),
            "analyses": analyses
        }
