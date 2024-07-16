# Groq-powered AI Chat

This project implements an interactive chat interface using the Groq API with the Llama3-8b-8192 model. It provides a command-line interface for users to interact with an AI assistant capable of various tasks, including file operations and code execution.

## Features

- Interactive chat with an AI powered by Groq's Llama3-8b-8192 model
- File system operations (create, read, and list files)
- Code execution in an isolated virtual environment
- Automode for continuous AI interaction
- Image path input (note: image processing not implemented)
- Conversation history tracking and saving
- Token usage monitoring
- Rich console interface for improved readability

## Requirements

- Python 3.7+
- Groq API key

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/groq-ai-chat.git
   cd groq-ai-chat
   ```

2. Install the required packages:
   ```
   pip install groq python-dotenv rich pillow
   ```

3. Create a `.env` file in the project root and add your Groq API key:
   ```
   GROQ_API_KEY=your_api_key_here
   ```

## Usage

Run the script using Python:

```
python groq-engineer.py
```

Once the chat interface starts, you can:

- Type your messages to interact with the AI
- Use special commands:
  - `exit`: End the conversation
  - `image`: Include an image in your message (path input only, processing not implemented)
  - `automode [number]`: Enter Autonomous mode with a specific number of iterations
  - `reset`: Clear the conversation history
  - `save chat`: Save the conversation to a Markdown file

You can also perform file operations by using natural language commands, such as:
- "create a file named example.txt with content: Hello, World!"
- "read the file example.txt"
- "list files in the current directory"

## Automode

Automode allows for continuous interaction with the AI for a specified number of iterations. To use automode:

1. Type `automode [number]` (e.g., `automode 5`)
2. Provide the initial goal or task for the AI
3. The AI will continue working on the task for the specified number of iterations or until completion
4. Press Ctrl+C at any time to exit automode

## Limitations

- Image processing is not implemented; the script only accepts image paths
- The AI's knowledge is based on its training data and may not have up-to-date information
- Token usage is estimated and may not precisely match Groq's actual token count

## Contributing

Contributions to improve the project are welcome. Please feel free to submit issues or pull requests.

## License

This project is open-source and available under the MIT License.
