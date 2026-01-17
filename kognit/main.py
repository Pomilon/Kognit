import argparse
import sys
import os
import traceback
from rich.console import Console
from rich.panel import Panel
from kognit.refinery.engine import synthesize_identity
from kognit.probes.github import GithubProbe
from kognit.probes.web import WebProbe
from kognit.probes.search import SearchProbe
from kognit.probes.normalizer import normalize_profile_context
from kognit.renderer.manifest import create_manifest
from kognit.renderer.engine import render_to_html
from weasyprint import HTML
from pdf2image import convert_from_path

console = Console()

def generate_preview_image(pdf_path: str):
    """
    Generates a PNG preview of the first page of the PDF.
    """
    try:
        images = convert_from_path(pdf_path, first_page=1, last_page=1)
        if images:
            png_path = pdf_path.replace(".pdf", ".png")
            images[0].save(png_path, "PNG")
            console.print(f"[bold green]Preview Generated: {png_path}[/bold green]")
    except Exception as e:
        console.print(f"[yellow]Could not generate PNG preview: {e}[/yellow]")

def main():
    parser = argparse.ArgumentParser(description="Kognit: Technical Biographer Agent")
    parser.add_argument("username", help="GitHub username to profile")
    parser.add_argument("--token", help="GitHub Personal Access Token (optional, overrides env)", default=None)
    parser.add_argument("--model", help="LLM model to use", default="google-gla:gemini-flash-latest")
    parser.add_argument("--output", help="Path to output PDF or HTML file", default="profile.pdf")
    parser.add_argument("--scrape-external", action="store_true", help="Attempt to scrape linked websites/blogs")
    parser.add_argument("--scraping-mode", choices=["auto", "api", "browser"], default="auto", 
                        help="Choose between GraphQL API (requires token) or Browser-like HTML scraping")
    parser.add_argument("--mode", choices=["summary", "deep-dive", "connections", "full-dive"], default="summary",
                        help="Analysis mode: 'summary' (default), 'deep-dive' (technical), 'connections' (ecosystem), or 'full-dive' (agentic exploration)")
    parser.add_argument("--instruction", help="Custom additional instructions for the AI agent", default=None)
    parser.add_argument("--humor", type=int, default=0, help="Humor level (0-100). 0 is professional, 100 is fully humorous.")
    parser.add_argument("--roast", action="store_true", help="Enable Roasting Mode. The agent will ruthlessly critique the profile.")
    
    args = parser.parse_args()

    # 1. Fetch GitHub Data
    # Update print to show tone
    tone_str = "Professional"
    if args.roast: tone_str = "[red]ROAST 🔥[/red]"
    elif args.humor > 0: tone_str = f"Humor: {args.humor}%"
    
    console.print(f"[bold blue]Kognit[/bold blue] - Targeting: [cyan]{args.username}[/cyan] | Mode: [magenta]{args.mode}[/magenta] | Tone: {tone_str}")
    
    # Determine scraping mode
    use_browser = False
    if args.scraping_mode == "browser":
        use_browser = True
    elif args.scraping_mode == "api":
        use_browser = False
    
    gh_probe = GithubProbe(token=args.token)
    try:
        with console.status(f"Fetching GitHub Identity ({args.scraping_mode})..."):
            force_browser = (args.scraping_mode == "browser")
            raw_github_data = gh_probe.fetch_profile(args.username, use_browser_scraping=force_browser)
            
    except Exception as e:
        console.print(f"[red]GitHub Probe Failed: {e}[/red]")
        sys.exit(1)

    # 2. Fetch External Data (Optional)
    external_content = {}
    if args.scrape_external:
        user_node = raw_github_data.get("data", {}).get("user", {})
        urls_to_scrape = []
        if user_node.get("websiteUrl"):
            urls_to_scrape.append(user_node.get("websiteUrl"))
        
        web_probe = WebProbe()
        with console.status(f"Scraping {len(urls_to_scrape)} external sources..."):
            for url in urls_to_scrape:
                if not url.startswith("http"):
                    continue # Skip invalid
                console.print(f"  - Probe: {url}")
                content = web_probe.scrape_page(url)
                if content:
                    external_content[url] = content

    # 3. Web Search (New)
    search_results = []
    if args.scrape_external: # reusing this flag or add a new one? Assuming implied by "external"
        try:
            search_probe = SearchProbe()
            with console.status("Performing Web Search..."):
                # We search for the username + real name if available
                user_node = raw_github_data.get("data", {}).get("user", {})
                query = f"{user_node.get('name', '')} {args.username}".strip()
                search_results = search_probe.search_developer(query)
        except Exception as e:
            console.print(f"[yellow]Web Search Failed: {e}[/yellow]")

    # 3. Normalize & Synthesize
    console.print("[bold yellow]Synthesizing Narrative...[/bold yellow]")
    
    # In full-dive, the ExplorerAgent analyzes READMEs and produces a condensed report.
    # We strip raw READMEs from the main context to avoid token overflow.
    include_readmes = (args.mode != "full-dive")
    
    normalized_context = normalize_profile_context(
        raw_github_data, 
        external_content, 
        search_results, 
        include_readmes=include_readmes
    )
    
    # --- Full Dive: Agentic Exploration ---
    if args.mode == "full-dive":
        try:
            from kognit.agent.explorer import ExplorerAgent
            console.print("[bold magenta]Initiating Full-Dive Exploration...[/bold magenta]")
            
            # Using same model as main synthesis for consistency
            explorer = ExplorerAgent(model_name=args.model, humor=args.humor, is_roast=args.roast)
            
            # We assume asyncio is needed. main() is sync, so we run the async method.
            # ExplorerAgent.full_dive is async.
            import asyncio
            dive_results = asyncio.run(explorer.full_dive(raw_github_data.get("data", {}).get("user", {})))
            
            # Pass a SUMMARY to the agent, not the full text, to save tokens.
            # We just list the repos analyzed and their scores/stack.
            dive_summary = "\n# Technical Audit Summary (Full details appended to report)\n"
            for analysis in dive_results["analyses"]:
                dive_summary += f"- {analysis.name}: Complexity {analysis.complexity_score}/10. Stack: {', '.join(analysis.key_technologies)}\n"
            
            normalized_context += "\n\n" + dive_summary
            
            # Switch to deep-dive mode for instructions, but we handle the report differently
            args.mode = "deep-dive" 
            
        except Exception as e:
            console.print(f"[red]Full Dive Failed: {e}[/red]")
            dive_results = None
            # Fallback to standard flow
    # --------------------------------------
    
    try:
        from kognit.refinery.engine import generate_identity_from_context
        
        identity = generate_identity_from_context(
            normalized_context, 
            model_name=args.model,
            mode=args.mode,
            custom_instructions=args.instruction,
            humor_level=args.humor,
            is_roast=args.roast
        )
        
        # Inject Full Dive Data directly
        if args.mode == "deep-dive" and 'dive_results' in locals() and dive_results:
             identity.repository_analyses = dive_results["analyses"]
        
        # --- Forced Consistency: Inject pre-determined data ---
        user_node = raw_github_data.get("data", {}).get("user", {})
        
        # 1. Guarantee Avatar
        if user_node.get("avatarUrl"):
            identity.avatar_url = user_node.get("avatarUrl")
            
        # 2. Guarantee Primary GitHub Link
        github_link = f"https://github.com/{args.username}"
        if github_link not in identity.external_links:
            identity.external_links.insert(0, github_link)
            
        # 3. Ensure name matches raw data if AI hallucinated it
        if user_node.get("name") and not identity.name:
            identity.name = user_node.get("name")
        # -----------------------------------------------------

        console.print(Panel(f"[bold green]{identity.name}[/bold green]\n[italic]{identity.headline}[/italic]", title="Identity Synthesized"))
        
        # 4. Render
        html_path = args.output.replace(".pdf", ".html")
        manifest = create_manifest(identity)
        render_to_html(manifest, html_path)
        
        if args.output.endswith(".pdf"):
            with console.status("Generating PDF..."):
                HTML(html_path).write_pdf(args.output)
            console.print(f"[bold green]PDF Generated: {args.output}[/bold green]")
            
            # Generate PNG Preview
            with console.status("Generating Preview..."):
                generate_preview_image(args.output)
        else:
            console.print(f"[bold green]Report Generated: {html_path}[/bold green]")

    except Exception as e:
        console.print(f"[red]Synthesis/Rendering Failed:[/red]")
        console.print(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
