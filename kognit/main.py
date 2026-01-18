import argparse
import sys
import os
import traceback
from rich.console import Console
from rich.panel import Panel
from kognit.refinery.engine import synthesize_identity
from kognit.probes.github import GithubProbe
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
    parser.add_argument("--scraping-mode", choices=["auto", "api", "browser"], default="auto", 
                        help="Choose between GraphQL API (requires token) or Browser-like HTML scraping")
    parser.add_argument("--mode", choices=["summary", "deep-dive", "connections", "full-dive"], default="summary",
                        help="Analysis mode: 'summary' (default), 'deep-dive' (technical), 'connections' (ecosystem), or 'full-dive'")
    parser.add_argument("--instruction", help="Custom additional instructions for the AI agent", default=None)
    parser.add_argument("--humor", type=int, default=0, help="Humor level (0-100). 0 is professional, 100 is fully humorous.")
    parser.add_argument("--roast", action="store_true", help="Enable Roasting Mode. The agent will ruthlessly critique the profile.")
    
    args = parser.parse_args()

    # --- Ethical Disclaimer & Confirmation ---
    disclaimer = Panel(
        "[bold red]ETHICAL DISCLAIMER & USAGE WARNING[/bold red]\n\n"
        "1. [bold]Anti-Stalking:[/bold] This tool must NOT be used to harass, stalk, or maliciousy profile individuals.\n"
        "2. [bold]Non-Professional:[/bold] Reports are AI-generated and should NOT be used for hiring or background checks.\n"
        "3. [bold]Subjectivity:[/bold] Persona narratives prioritize creativity over strict factual accuracy.\n"
        "4. [bold]Liability:[/bold] The developer is not responsible for any social or professional consequences.\n\n"
        "Do you agree to use Kognit responsibly and ethically?",
        title="⚠️ Kognit Terms of Use",
        border_style="yellow"
    )
    console.print(disclaimer)
    
    confirm = console.input("[bold cyan]Type 'yes' to proceed, or anything else to exit: [/bold cyan]")
    if confirm.lower() != "yes":
        console.print("[red]Exit: Agreement declined.[/red]")
        sys.exit(0)
    
    if args.roast:
        console.print("\n[bold red]🔥 WARNING:[/bold red] Roast Mode is active. The following content will be critical and satirical. [italic]Proceed with a thick skin.[/italic]\n")
    # ------------------------------------------

    # 1. Fetch GitHub Data
    tone_str = "Professional"
    if args.roast: tone_str = "[red]ROAST 🔥[/red]"
    elif args.humor > 0: tone_str = f"Humor: {args.humor}%"
    
    console.print(f"[bold blue]Kognit[/bold blue] - Targeting: [cyan]{args.username}[/cyan] | Mode: [magenta]{args.mode}[/magenta] | Tone: {tone_str}")
    
    gh_probe = GithubProbe(token=args.token)
    try:
        with console.status(f"Fetching GitHub Identity ({args.scraping_mode})..."):
            force_browser = (args.scraping_mode == "browser")
            raw_github_data = gh_probe.fetch_profile(args.username, use_browser_scraping=force_browser)
            
    except Exception as e:
        console.print(f"[red]GitHub Probe Failed: {e}[/red]")
        sys.exit(1)

    # 2. Normalize & Synthesize
    console.print("[bold yellow]Synthesizing Narrative...[/bold yellow]")
    
    include_readmes = (args.mode != "full-dive")
    
    normalized_context = normalize_profile_context(
        raw_github_data, 
        include_readmes=include_readmes
    )
    
    # --- Full Dive: Agentic Exploration ---
    if args.mode == "full-dive":
        try:
            from kognit.agent.explorer import ExplorerAgent
            console.print("[bold magenta]Initiating Full-Dive Exploration...[/bold magenta]")
            
            explorer = ExplorerAgent(model_name=args.model, humor=args.humor, is_roast=args.roast)
            
            import asyncio
            dive_results = asyncio.run(explorer.full_dive(raw_github_data.get("data", {}).get("user", {})))
            
            dive_summary = "\n# Technical Audit Summary (Full details appended to report)\n"
            for analysis in dive_results["analyses"]:
                dive_summary += f"- {analysis.name}: Complexity {analysis.complexity_score}/10. Stack: {', '.join(analysis.key_technologies)}\n"
            
            normalized_context += "\n\n" + dive_summary
            args.mode = "deep-dive" 
            
        except Exception as e:
            console.print(f"[red]Full Dive Failed: {e}[/red]")
            dive_results = None
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
        
        # Inject Full Dive Data
        if args.mode == "deep-dive" and 'dive_results' in locals() and dive_results:
             identity.repository_analyses = dive_results["analyses"]

        # Forced Consistency
        user_node = raw_github_data.get("data", {}).get("user", {})
        if user_node.get("avatarUrl"):
            identity.avatar_url = user_node.get("avatarUrl")
        github_link = f"https://github.com/{args.username}"
        if github_link not in identity.external_links:
            identity.external_links.insert(0, github_link)
        if user_node.get("name") and not identity.name:
            identity.name = user_node.get("name")

        console.print(Panel(f"[bold green]{identity.name}[/bold green]\n[italic]{identity.headline}[/italic]", title="Identity Synthesized"))
        
        # 3. Render
        html_path = args.output.replace(".pdf", ".html")
        manifest = create_manifest(identity)
        render_to_html(manifest, html_path)
        
        if args.output.endswith(".pdf"):
            with console.status("Generating PDF..."):
                HTML(html_path).write_pdf(args.output)
            console.print(f"[bold green]PDF Generated: {args.output}[/bold green]")
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