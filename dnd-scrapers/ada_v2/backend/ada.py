import asyncio
import base64
import json
import os
import sys
import traceback
import time
from dotenv import load_dotenv
from openai import AsyncOpenAI  # We use OpenAI client to talk to Ollama

# --- LOCAL AI CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/v1"
MODEL_NAME = "llama3"  # Make sure you ran `ollama run llama3`
SYSTEM_PROMPT = (
    "You are Ada, an Advanced Design Assistant. "
    "You control a computer to help the user with CAD, Web Browsing, and Smart Home tasks. "
    "You are witty, concise, and professional."
)

# --- TOOLS DEFINITIONS (Preserved) ---
from tools import tools_list

# Import your Agents
from cad_agent import CadAgent
from web_agent import WebAgent
from kasa_agent import KasaAgent
from printer_agent import PrinterAgent

# ... [Keep your tool definitions like generate_cad, run_web_agent here] ...
# For brevity, I am reusing the definitions you already have. 
# In the actual file, paste your tool definitions (generate_cad, etc.) back here.
# <PASTE YOUR TOOL DICTIONARIES HERE>

# --- ADAPTER: Convert Google Tools to OpenAI/Ollama Format ---
def convert_tools_to_openai(google_tools_list):
    openai_tools = []
    # This handles the specific structure from your file
    source_list = google_tools_list[1]["function_declarations"] 
    
    for tool in source_list:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"]
            }
        })
    return openai_tools

class AudioLoop:
    def __init__(self, video_mode="none", on_audio_data=None, on_video_frame=None, on_cad_data=None, on_web_data=None, on_transcription=None, on_tool_confirmation=None, on_cad_status=None, on_cad_thought=None, on_project_update=None, on_device_update=None, on_error=None, input_device_index=None, input_device_name=None, output_device_index=None, kasa_agent=None):
        
        # Callbacks (Preserved so Frontend still works)
        self.on_cad_data = on_cad_data
        self.on_web_data = on_web_data
        self.on_transcription = on_transcription
        self.on_cad_status = on_cad_status
        self.on_cad_thought = on_cad_thought
        self.on_project_update = on_project_update
        self.on_device_update = on_device_update
        self.on_tool_confirmation = on_tool_confirmation
        
        # Initialize Agents
        self.cad_agent = CadAgent(on_thought=on_cad_thought, on_status=on_cad_status)
        self.web_agent = WebAgent()
        self.kasa_agent = kasa_agent if kasa_agent else KasaAgent()
        self.printer_agent = PrinterAgent()
        
        # Initialize Project Manager
        from project_manager import ProjectManager
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        self.project_manager = ProjectManager(project_root)

        # Local AI Client
        self.client = AsyncOpenAI(base_url=OLLAMA_URL, api_key="ollama")
        
        # Tool List conversion
        # We assume 'tools' variable exists from your original code snippet
        # If not, recreate the list [generate_cad, run_web_agent, ...]
        self.available_functions = {
            "generate_cad": self.handle_cad_request,
            "run_web_agent": self.handle_web_agent_request,
            "list_smart_devices": self.handle_list_devices, # You need to wrap these
             # Map other tools here...
        }

    # --- WRAPPER FUNCTIONS (Map Tool calls to Agents) ---
    async def handle_cad_request(self, args):
        prompt = args.get("prompt")
        if self.on_transcription: self.on_transcription({"sender": "ADA", "text": f"Generating CAD: {prompt}..."})
        
        cad_output_dir = str(self.project_manager.get_current_project_path() / "cad")
        data = await self.cad_agent.generate_prototype(prompt, output_dir=cad_output_dir)
        
        if data and self.on_cad_data:
            self.on_cad_data(data)
        return "CAD Model generated and displayed to user."

    async def handle_web_agent_request(self, args):
        prompt = args.get("prompt")
        async def update_fe(img, log):
            if self.on_web_data: self.on_web_data({"image": img, "log": log})
        
        result = await self.web_agent.run_task(prompt, update_callback=update_fe)
        return f"Web Task Finished: {result}"

    async def handle_list_devices(self, args):
        # Simply return text, Kasa agent logic goes here
        return "Smart home devices listed (Local stub)."

    # --- THE BRAIN LOOP ---
    async def run(self, start_message=None):
        print(f"[ADA LOCAL] Connected to {OLLAMA_URL} using {MODEL_NAME}")
        
        # Chat History Context
        history = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        
        while True:
            try:
                # 1. GET INPUT (Text for now, Voice later)
                # Using `aioconsole` or simple input() in a thread would be better, 
                # but for simplicity we block here or use a dummy input mechanism.
                user_input = await asyncio.to_thread(input, "\n[YOU]: ")
                
                if user_input.lower() in ["exit", "quit"]: break

                # Update Context
                history.append({"role": "user", "content": user_input})
                if self.on_transcription: self.on_transcription({"sender": "User", "text": user_input})

                # 2. THINK (Ollama)
                print("[ADA] Thinking...")
                # Note: We need to properly format tools for Llama3 or use a model that supports them well.
                # For standard Llama3, we might need a raw prompt, but let's try standard API.
                response = await self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=history,
                    # tools=convert_tools_to_openai(...), # Uncomment if using a tool-calling supported model (like mistral-nemo)
                )

                response_message = response.choices[0].message
                content = response_message.content

                # 3. HANDLE TOOLS (Manual check if model doesn't support native tool calling)
                # If content contains JSON or special markers, parse it.
                # For now, we assume direct chat.

                # 4. SPEAK / OUTPUT
                print(f"[ADA]: {content}")
                history.append({"role": "assistant", "content": content})
                
                if self.on_transcription: 
                    self.on_transcription({"sender": "ADA", "text": content})

            except Exception as e:
                print(f"Error in loop: {e}")
                traceback.print_exc()

if __name__ == "__main__":
    # Simple runner
    loop = AudioLoop()
    asyncio.run(loop.run())
