import os
import re
import markdown
import matplotlib.pyplot as plt
import io
from jinja2 import Environment, FileSystemLoader
from kognit.renderer.manifest import RenderManifest

def render_to_html(manifest: RenderManifest, output_path: str):
    """
    Renders the manifest to an HTML file, converting Markdown fields to HTML.
    """
    identity = manifest.identity
    
    def latex_to_svg(latex_str, fontsize=12):
        """
        Renders a LaTeX string to an SVG using Matplotlib.
        """
        try:
            # Create a dummy figure
            fig = plt.figure(figsize=(0.01, 0.01))
            # Render text. We use raw strings. 
            # Matplotlib requires $...$ for math mode.
            # If the input doesn't have $, we wrap it.
            if not latex_str.startswith('$'):
                latex_str = f"${latex_str}$"
                
            text = fig.text(0.5, 0.5, latex_str, fontsize=fontsize, ha='center', va='center')
            
            # Save to buffer
            buf = io.BytesIO()
            fig.savefig(buf, format='svg', bbox_inches='tight', pad_inches=0.05, transparent=True)
            plt.close(fig)
            
            svg_data = buf.getvalue().decode('utf-8')
            
            # Matplotlib SVG includes a lot of XML headers, we strip them to inline it
            # Start from <svg
            start_idx = svg_data.find('<svg')
            if start_idx != -1:
                svg_data = svg_data[start_idx:]
                
            return svg_data
        except Exception as e:
            print(f"LaTeX Rendering Error: {e}")
            plt.close(fig)
            return f"<code>{latex_str}</code>" # Fallback

    def process_math(text):
        if not text: return ""
        
        # Function to replace block math $$...$$
        def replace_block(match):
            latex = match.group(1)
            svg = latex_to_svg(latex, fontsize=14)
            return f'<div class="math-block" style="text-align: center; margin: 15px 0;">{svg}</div>'

        # Function to replace inline math $...$
        def replace_inline(match):
            latex = match.group(1)
            svg = latex_to_svg(latex, fontsize=10)
            return f'<span class="math-inline" style="vertical-align: middle;">{svg}</span>'

        # Process Block Math first
        text = re.sub(r'\$\$([\s\S]+?)\$\$', replace_block, text)
        
        # Process Inline Math (non-greedy)
        text = re.sub(r'\$([^$]+?)\$', replace_inline, text)
        
        return text

    # Helper to safely convert
    def md(text):
        if not text: return ""
        # 1. Process Math -> SVG
        text_with_math = process_math(text)
        # 2. Markdown -> HTML
        return markdown.markdown(text_with_math, extensions=['extra'])

    # Process repository analyses markdown if present
    processed_repos = []
    if identity.repository_analyses:
        for repo in identity.repository_analyses:
            # We clone/copy to avoid mutating original
            processed_repos.append({
                "name": repo.name,
                "summary": repo.summary,
                "technical_deconstruction": md(repo.technical_deconstruction),
                "key_technologies": repo.key_technologies,
                "complexity_score": repo.complexity_score
            })

    processed_identity = {
        "name": identity.name,
        "avatar_url": identity.avatar_url,
        "headline": identity.headline,
        "summary": md(identity.summary),
        "technical_dna": identity.technical_dna,
        "project_highlights": identity.project_highlights, 
        "role_inference": identity.role_inference,
        "external_links": identity.external_links,
        "technical_depth_report": md(identity.technical_depth_report),
        "ecosystem_report": md(identity.ecosystem_report),
        "repository_analyses": processed_repos
    }
    
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('biography.html')
    
    render_context = {
        "manifest": {
            "identity": processed_identity,
            "theme": manifest.theme,
            "typography": manifest.typography,
            "assets": manifest.assets
        }
    }
    
    html_content = template.render(**render_context)
    
    with open(output_path, 'w') as f:
        f.write(html_content)
    
    return output_path