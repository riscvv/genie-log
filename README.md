# Logenius: AI-Powered Log Analysis Chatbot

## Introduction

Logenius is an innovative AI-powered chatbot designed to 
revolutionize log analysis in complex multi-component systems. 

By providing a natural language interface, Logenius supports common tasks 
such as system status inquiries, historical data retrieval, and error triage. 

Built on the Genie Worksheet framework and leveraging Structured and Unstructured Query Language, 
Logenius enhances contextual understanding of log data. 

With its advanced analysis capabilities and the `is_relevant()` API extension, 
Logenius streamlines the troubleshooting process, empowering engineers of all expertise levels 
to maintain critical system operations efficiently.


## Installation

To install Logenius, follow these steps:

1. Clone the repository:
   ```bash
   git clone https://github.com/riscvv/genie-log.git
   ```

2. Navigate to the project directory:
   ```bash
   cd genie-log
   ```

3. To install, we recommend using uv ([UV installation guide](https://github.com/astral-sh/uv?tab=readme-ov-file#installation)):
   ```bash
    uv venv
    source venv/bin/activate
    uv sync
   ```

4. Set up the necessary environment variables:
   ```bash
   export OPENAI_API_KEY=your_api_key_here
   ```

5. Initialize the database:

Refer to [systemChatBot repo README.md](https://github.com/riscvv/System-Triage-and-Monitor-ChatBot) for database construction and data dumping

## Running the Code

1. Prerequisite: Run SUQL-turbo in the directory. Please refer to [suql-turbo repo README.md](https://github.com/xiaofuhu/suql-turbo)

2. To run Logenius, execute the following command in the project directory:
```bash
cd experiments/agents/system_triage
python logenius.py
```