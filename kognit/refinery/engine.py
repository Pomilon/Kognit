import os
from typing import Optional, Union
from pydantic_ai import Agent, RunContext
from kognit.models.identity import DeveloperIdentity
from kognit.probes.normalizer import normalize_profile_context
from dotenv import load_dotenv

load_dotenv()

# --- Prompts ---

BASE_PROMPT = """
You are the Kognit Synthesis Engine. Your goal is to analyze the provided raw data from a developer's digital footprint.
Voice: Professional, objective, and analytical.

**CRITICAL INSTRUCTION:**
You MUST output your response by calling the valid tool/function that matches the `DeveloperIdentity` schema. 
Do NOT reply with plain markdown text. You must structured your answer inside the function call.
"""

SUMMARY_INSTRUCTIONS = """
**Mode: General Summary**
1. **Focus on Impact:** Explain the 'So What?'.
2. **Identify Patterns:** Notice technical habits and preferred stacks.
3. **Output:** Complete the core fields (summary, technical_dna, project_highlights).
"""

DEEP_DIVE_INSTRUCTIONS = """
**Mode: Extreme Deep Technical Analysis**
1. **Granular Analysis:** Do not summarize. Deconstruct. You must analyze the provided README snippets with extreme technical granularity. Look for specific architectural patterns, algorithmic choices, and system-level decisions.
2. **Citation:** When possible, quote specific technical claims or code concepts from the source material to back your analysis.
3. **Comprehensive Scope:** Analyze BOTH Pinned Projects AND the "Top Repositories". Do not ignore the unpinned repos if they contain technical signal.
4. **CRITICAL:** You MUST populate the `technical_depth_report` field. It should be a massive, detailed markdown report (1000+ words target).
   - **Architecture:** Explain *how* their systems work, not just what they do. Analyze data structures, concurrency models, and module interactions.
   - **Complexity:** Evaluate the difficulty of the problems solved (e.g., low-level optimizations, distributed state management, or complex algorithmic implementations).
   - **Quality:** Infer engineering standards from their tooling choices (CI, Testing, Documentation).
"""

CONNECTIONS_INSTRUCTIONS = """
**Mode: Ecosystem & Connections**
1. **Analyze Reach:** Look at stars, forks, and followers to gauge community impact.
2. **Network:** Identify organizations, key collaborators (inferred), and ecosystem position (e.g., "Core contributor to Rust ecosystem").
3. **Output:** MUST populate the `ecosystem_report` field with a detailed analysis of their place in the software world.
"""

# (Agent will be instantiated dynamically in generate_identity_from_context)

from kognit.refinery.validator import refine_identity

def generate_identity_from_context(
    context_str: str, 
    model_name: Optional[str] = None,
    mode: str = "summary",
    custom_instructions: Optional[str] = None,
    humor_level: int = 0,
    is_roast: bool = False
) -> DeveloperIdentity:
    """
    Directly synthesizes identity from a pre-normalized context string with specific mode instructions.
    """
    
    # Select Mode Instructions
    if mode == "deep-dive":
        mode_prompt = DEEP_DIVE_INSTRUCTIONS
    elif mode == "connections":
        mode_prompt = CONNECTIONS_INSTRUCTIONS
    else:
        mode_prompt = SUMMARY_INSTRUCTIONS

    # Construct Full Prompt
    full_system_prompt = f"{BASE_PROMPT}\n\n{mode_prompt}"
    
    # Inject Tone
    if is_roast:
        full_system_prompt += """
        \n**TONE SETTING: ROAST 🔥**
        - You are a merciless technical critic.
        - Roast the developer's tech stack, commit history, and bio.
        - Be savage, cynical, and technically accurate.
        - If they use 'trendy' tools, mock them for following hype.
        - If they use 'old' tools, mock them for being dinosaurs.
        - Your output should be a scathing critique, not a biography.
        """
    elif humor_level > 0:
        full_system_prompt += f"""
        \n**TONE SETTING: Humorous (Level {humor_level}/100)**
        - Inject wit and technical jokes proportional to the level.
        - Level 100 is full stand-up comedy.
        - Level 50 is witty and sarcastic but professional.
        - Keep the technical facts accurate, but make the delivery entertaining.
        """
    
    if custom_instructions:
        full_system_prompt += f"\n\n**User Custom Instructions:**\n{custom_instructions}"

    # Optimization: Re-instantiate agent to set system prompt cleanly
    agent = Agent(
        model_name or 'google-gla:gemini-flash-latest',
        output_type=DeveloperIdentity,
        system_prompt=full_system_prompt
    )
    
    result = agent.run_sync(
        f"Analyze the following developer footprint:\n\n{context_str}"
    )
    
    # --- Integration: Validate and Refine ---
    identity = refine_identity(result.output, context_str)
    
    return identity

def synthesize_identity(raw_github_payload: dict, model_name: Optional[str] = None) -> DeveloperIdentity:
    """
    Legacy entry point.
    """
    context = normalize_profile_context(raw_github_payload, {{}})
    return generate_identity_from_context(context, model_name)
