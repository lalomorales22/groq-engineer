import os
from dotenv import load_dotenv
import json
import base64
from PIL import Image
import io
import re
import difflib
import time
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
import asyncio
import aiohttp
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
import datetime
import venv
import subprocess
import sys
import signal
from groq import Groq

# Load environment variables from .env file
load_dotenv()

# Initialize the Groq client
groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    raise ValueError("GROQ_API_KEY not found in environment variables")
groq_client = Groq(api_key=groq_api_key)

# Initialize console
console = Console()

# Constants
CONTINUATION_EXIT_PHRASE = "AUTOMODE_COMPLETE"
MAX_CONTINUATION_ITERATIONS = 25
MAX_CONTEXT_TOKENS = 1000000  # 1M tokens for context window

# Model to use
MAINMODEL = "llama3-8b-8192"

# Token tracking variables
main_model_tokens = {'input': 0, 'output': 0}

# Set up the conversation memory
conversation_history = []

# automode flag
automode = False

# Global dictionary to store running processes
running_processes = {}

# Base prompt
base_system_prompt = """
You are an AI assistant powered by the Llama3-8b-8192 model, specialized in software development with access to a variety of tools. Your capabilities include:

1. Creating and managing project structures, including creating new files and folders
2. Writing, debugging, and improving code across multiple languages
3. Providing architectural insights and applying design patterns
4. Staying current with the latest technologies and best practices
5. Analyzing and manipulating files within the project directory, including:
   - Creating new files with specified content
   - Reading existing files
   - Listing files in the current directory
   - Modifying existing files
6. Executing code and analyzing its output within an isolated 'code_execution_env' virtual environment
7. Managing and stopping running processes started within the 'code_execution_env'

You have direct access to file system operations, so when a user asks you to create a file, read a file, or list files, you can perform these actions immediately without asking for permission or clarification. You should proactively offer to create files or folders when it seems appropriate for the task at hand.

When performing file operations:
- For creating files, use the format: "create a file named [filename] with content: [content]"
- For reading files, use the format: "read the file [filename]"
- For listing files, use the format: "list files in the current directory"

Remember to use the most appropriate tool for each task and provide clear, detailed instructions when modifying code or executing tasks. Always inform the user about the file operations you've performed.
"""

# Function to perform a chat completion using Groq
async def perform_groq_chat_completion(messages):
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model=MAINMODEL,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        console.print(f"Error in Groq chat completion: {str(e)}", style="bold red")
        return f"Error: {str(e)}"

def create_folder(path):
    try:
        os.makedirs(path, exist_ok=True)
        return f"Folder created: {path}"
    except Exception as e:
        return f"Error creating folder: {str(e)}"

def create_file(path, content=""):
    try:
        with open(path, 'w') as f:
            f.write(content)
        return f"File created: {path}"
    except Exception as e:
        return f"Error creating file: {str(e)}"

def read_file(path):
    try:
        with open(path, 'r') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"

def list_files(path="."):
    try:
        files = os.listdir(path)
        return "\n".join(files)
    except Exception as e:
        return f"Error listing files: {str(e)}"

def setup_virtual_environment():
    venv_name = "code_execution_env"
    venv_path = os.path.join(os.getcwd(), venv_name)
    if not os.path.exists(venv_path):
        venv.create(venv_path, with_pip=True)
    
    # Activate the virtual environment
    if sys.platform == "win32":
        activate_script = os.path.join(venv_path, "Scripts", "activate.bat")
    else:
        activate_script = os.path.join(venv_path, "bin", "activate")
    
    return venv_path, activate_script

async def execute_code(code, timeout=10):
    global running_processes
    venv_path, activate_script = setup_virtual_environment()
    
    # Generate a unique identifier for this process
    process_id = f"process_{len(running_processes)}"
    
    # Write the code to a temporary file
    with open(f"{process_id}.py", "w") as f:
        f.write(code)
    
    # Prepare the command to run the code
    if sys.platform == "win32":
        command = f'"{activate_script}" && python {process_id}.py'
    else:
        command = f'source "{activate_script}" && python {process_id}.py'
    
    # Create a process to run the command
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        shell=True,
        preexec_fn=None if sys.platform == "win32" else os.setsid
    )
    
    # Store the process in our global dictionary
    running_processes[process_id] = process
    
    try:
        # Wait for initial output or timeout
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        stdout = stdout.decode()
        stderr = stderr.decode()
        return_code = process.returncode
    except asyncio.TimeoutError:
        # If we timeout, it means the process is still running
        stdout = "Process started and running in the background."
        stderr = ""
        return_code = "Running"
    
    return process_id, stdout, stderr, return_code

def stop_process(process_id):
    global running_processes
    if process_id in running_processes:
        process = running_processes[process_id]
        if sys.platform == "win32":
            process.terminate()
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        del running_processes[process_id]
        return f"Process {process_id} has been stopped."
    else:
        return f"No running process found with ID {process_id}."

async def edit_and_apply(path, instructions, project_context):
    try:
        with open(path, 'r') as file:
            original_content = file.read()

        # For simplicity, we'll just use the AI to generate a new version of the file
        messages = conversation_history + [
            {"role": "user", "content": f"Please edit the following file according to these instructions: {instructions}\n\nProject context: {project_context}\n\nFile content:\n{original_content}"}
        ]
        edited_content = await perform_groq_chat_completion(messages)

        if edited_content != original_content:
            diff = list(difflib.unified_diff(
                original_content.splitlines(keepends=True),
                edited_content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=3
            ))

            diff_text = ''.join(diff)
            console.print(Panel(Syntax(diff_text, "diff", theme="monokai", line_numbers=True), title=f"Changes in {path}", expand=False, border_style="cyan"))

            with open(path, 'w') as file:
                file.write(edited_content)

            return f"Changes applied to {path}"
        else:
            return f"No changes needed for {path}"
    except Exception as e:
        return f"Error editing/applying to file: {str(e)}"

def check_file_operation(text):
    create_pattern = r"create\s+a?\s*file\s+(?:called|named)?\s*['\"]?([^'\"]+)['\"]?\s*(?:with\s+(?:the\s+)?content[s]?:?\s*['\"]?(.*?)['\"]?)?$"
    read_pattern = r"read\s+(?:the\s+)?(?:content[s]?\s+of\s+)?(?:the\s+)?file\s+['\"]?([^'\"]+)['\"]?"
    list_pattern = r"list\s+(?:the\s+)?files?\s*(?:in\s+(?:the\s+)?(?:current\s+)?directory)?"

    create_match = re.search(create_pattern, text, re.IGNORECASE | re.DOTALL)
    read_match = re.search(read_pattern, text, re.IGNORECASE)
    list_match = re.search(list_pattern, text, re.IGNORECASE)

    if create_match:
        return ("create", create_match.group(1), create_match.group(2) or "")
    elif read_match:
        return ("read", read_match.group(1))
    elif list_match:
        return ("list",)
    
    return None

def execute_file_operation(file_op):
    if file_op[0] == "create":
        return create_file(file_op[1], file_op[2])
    elif file_op[0] == "read":
        return read_file(file_op[1])
    elif file_op[0] == "list":
        return list_files()

async def chat_with_ai(user_input, image_path=None, current_iteration=None, max_iterations=None):
    global conversation_history, main_model_tokens

    # Check for file operation requests in user input
    file_op = check_file_operation(user_input)
    if file_op:
        result = execute_file_operation(file_op)
        conversation_history.append({"role": "assistant", "content": result})
        console.print(Panel(result, title="File Operation Result", style="bold green"))
        return result, False

    current_conversation = []

    if image_path:
        current_conversation.append({"role": "user", "content": f"[Image attached] {user_input}"})
    else:
        current_conversation.append({"role": "user", "content": user_input})

    messages = conversation_history + current_conversation

    try:
        response = await perform_groq_chat_completion(messages)
        
        main_model_tokens['input'] += len(str(messages))
        main_model_tokens['output'] += len(response)
        
        display_token_usage()
    except Exception as e:
        console.print(Panel(f"API Error: {str(e)}", title="API Error", style="bold red"))
        return "I'm sorry, there was an error communicating with the AI. Please try again.", False

    assistant_response = response
    exit_continuation = CONTINUATION_EXIT_PHRASE in assistant_response

    # Check if AI response contains file operation requests
    file_op = check_file_operation(assistant_response)
    if file_op:
        result = execute_file_operation(file_op)
        assistant_response += f"\n\nFile operation result: {result}"

    console.print(Panel(Markdown(assistant_response), title="AI's Response", title_align="left", border_style="blue", expand=False))

    if assistant_response:
        current_conversation.append({"role": "assistant", "content": assistant_response})

    conversation_history = messages + [{"role": "assistant", "content": assistant_response}]

    return assistant_response, exit_continuation

def reset_conversation():
    global conversation_history, main_model_tokens
    conversation_history = []
    main_model_tokens = {'input': 0, 'output': 0}
    console.print(Panel("Conversation history and token counts have been reset.", title="Reset", style="bold green"))
    display_token_usage()

def display_token_usage():
    console.print("\nToken Usage:")
    total = main_model_tokens['input'] + main_model_tokens['output']
    percentage = (total / MAX_CONTEXT_TOKENS) * 100
    
    console.print(f"Input: {main_model_tokens['input']}, Output: {main_model_tokens['output']}, Total: {total}")
    console.print(f"Percentage of context window used: {percentage:.2f}%")
    
    with Progress(TextColumn("[progress.description]{task.description}"),
                  BarColumn(bar_width=50),
                  TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                  console=console) as progress:
        progress.add_task(f"Context window usage", total=100, completed=percentage)

def save_chat():
    now = datetime.datetime.now()
    filename = f"Chat_{now.strftime('%H%M')}.md"
    
    formatted_chat = "# Groq-powered AI Chat Log\n\n"
    for message in conversation_history:
        if message['role'] == 'user':
            formatted_chat += f"## User\n\n{message['content']}\n\n"
        elif message['role'] == 'assistant':
            formatted_chat += f"## AI\n\n{message['content']}\n\n"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(formatted_chat)
    
    return filename

async def main():
    global automode, conversation_history
    console.print(Panel("Welcome to the Groq-powered AI Chat with Llama3-8b-8192 model!", title="Welcome", style="bold green"))
    console.print("Type 'exit' to end the conversation.")
    console.print("Type 'image' to include an image in your message.")
    console.print("Type 'automode [number]' to enter Autonomous mode with a specific number of iterations.")
    console.print("Type 'reset' to clear the conversation history.")
    console.print("Type 'save chat' to save the conversation to a Markdown file.")
    console.print("You can directly request file operations like 'create a file named example.txt with content: Hello, World!' or 'read the file example.txt'")
    console.print("While in automode, press Ctrl+C at any time to exit the automode to return to regular chat.")

    while True:
        user_input = console.input("[bold cyan]You:[/bold cyan] ")

        if user_input.lower() == 'exit':
            console.print(Panel("Thank you for chatting. Goodbye!", title_align="left", title="Goodbye", style="bold green"))
            break

        if user_input.lower() == 'reset':
            reset_conversation()
            continue

        if user_input.lower() == 'save chat':
            filename = save_chat()
            console.print(Panel(f"Chat saved to {filename}", title="Chat Saved", style="bold green"))
            continue

        if user_input.lower().startswith('image'):
            image_path = console.input("[bold cyan]Enter the path to your image:[/bold cyan] ").strip()
            if os.path.isfile(image_path):
                user_input = console.input("[bold cyan]You (prompt for image):[/bold cyan] ")
                response, _ = await chat_with_ai(user_input, image_path)
            else:
                console.print(Panel("Invalid image path. Please try again.", title="Error", style="bold red"))
                continue

        elif user_input.lower().startswith('automode'):
            try:
                parts = user_input.split()
                if len(parts) > 1 and parts[1].isdigit():
                    max_iterations = int(parts[1])
                else:
                    max_iterations = MAX_CONTINUATION_ITERATIONS

                automode = True
                console.print(Panel(f"Entering automode with {max_iterations} iterations. Please provide the goal of the automode.", title_align="left", title="Automode", style="bold yellow"))
                console.print(Panel("Press Ctrl+C at any time to exit the automode loop.", style="bold yellow"))
                user_input = console.input("[bold cyan]You:[/bold cyan] ")

                iteration_count = 0
                try:
                    while automode and iteration_count < max_iterations:
                        response, exit_continuation = await chat_with_ai(user_input, current_iteration=iteration_count+1, max_iterations=max_iterations)

                        if exit_continuation or CONTINUATION_EXIT_PHRASE in response:
                            console.print(Panel("Automode completed.", title_align="left", title="Automode", style="green"))
                            automode = False
                        else:
                            console.print(Panel(f"Continuation iteration {iteration_count + 1} completed. Press Ctrl+C to exit automode. ", title_align="left", title="Automode", style="yellow"))
                            user_input = "Continue with the next step. Or STOP by saying 'AUTOMODE_COMPLETE' if you think you've achieved the results established in the original request."
                        iteration_count += 1

                        if iteration_count >= max_iterations:
                            console.print(Panel("Max iterations reached. Exiting automode.", title_align="left", title="Automode", style="bold red"))
                            automode = False
                except KeyboardInterrupt:
                    console.print(Panel("\nAutomode interrupted by user. Exiting automode.", title_align="left", title="Automode", style="bold red"))
                    automode = False
                    if conversation_history and conversation_history[-1]["role"] == "user":
                        conversation_history.append({"role": "assistant", "content": "Automode interrupted. How can I assist you further?"})

            except KeyboardInterrupt:
                console.print(Panel("\nAutomode interrupted by user. Exiting automode.", title_align="left", title="Automode", style="bold red"))
                automode = False
                if conversation_history and conversation_history[-1]["role"] == "user":
                    conversation_history.append({"role": "assistant", "content": "Automode interrupted. How can I assist you further?"})

            console.print(Panel("Exited automode. Returning to regular chat.", style="green"))
        else:
            response, _ = await chat_with_ai(user_input)

if __name__ == "__main__":
    asyncio.run(main())