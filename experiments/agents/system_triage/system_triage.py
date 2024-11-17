import asyncio
import os
import random
from uuid import uuid4

import yaml
from suql.agent import postprocess_suql

from worksheets.agent import Agent
from worksheets.environment import get_genie_fields_from_ws
from worksheets.interface_utils import conversation_loop
from worksheets.knowledge import SUQLKnowledgeBase, SUQLReActParser, SUQLParser

with open("model_config.yaml", "r") as f:
    model_config = yaml.safe_load(f)

# Define your APIs
course_is_full = {}


def book_restaurant_yelp(
    restaurant: str,
    **kwargs,
):
    outcome = {
        "status": "success",
    }
    return outcome
#
#
# def course_detail_to_individual_params(course_detail):
#     if course_detail.value is None:
#         return {}
#     course_detail = course_detail.value
#     course_detail = {}
#     for field in get_genie_fields_from_ws(course_detail):
#         course_detail[field.name] = field.value
#
#     return course_detail
#
#
# def courses_to_take_oval(**kwargs):
#     return {"success": True, "transaction_id": uuid4()}
#
#
# def is_course_full(course_id, **kwargs):
#     # randomly return True or False
#     if course_id not in course_is_full:
#         is_full = random.choice([True, False])
#         course_is_full[course_id] = is_full
#
#     return course_is_full[course_id]


# Define path to the prompts

current_dir = os.path.dirname(os.path.realpath(__file__))
prompt_dir = os.path.join(current_dir, "prompts")


# Define Knowledge Base
suql_knowledge = SUQLKnowledgeBase(
    llm_model_name="gpt-4o", # model name, use this to for _answer, _summary
    tables_with_primary_keys={
        "log_records": "line_id",
        "log_templates": "event_id"
    },
    database_name="postgres", # database name
    embedding_server_address="http://127.0.0.1:8501",  # embedding server address for free text
    source_file_mapping={
        "system_triage_general_info.txt": os.path.join(
            current_dir, "system_triage_general_info.txt"
        ) # mapping of free-text files with the path
    },
    # db_host="localhost", # database host
    # db_port="5432", # database port
    postprocessing_fn=postprocess_suql,  # optional postprocessing function
    result_postprocessing_fn=None,  # optional result postprocessing function
)

# Define Simple LLM Parser
suql_parser = SUQLParser(
    llm_model_name="gpt-4o",
    prompt_selector=None,  # optional function that helps in selecting the right prompt
    knowledge=suql_knowledge,
)

# Define the SUQL React Parser
# slower but better for suql query generation, design decision
# suql_react_parser = SUQLReActParser(
#     llm_model_name="gpt-4o",  # model name
#     example_path=os.path.join(current_dir, "examples.txt"),  # path to examples
#     instruction_path=os.path.join(current_dir, "instructions.txt"),  # path to domain-specific instructions
#     table_schema_path=os.path.join(current_dir, "table_schema.txt"),  # path to table schema
#     knowledge=suql_knowledge,  # previously defined knowledge source
# )

# Define the agent
system_triage_bot = Agent(
    botname="System Triage Assistant",
    description="You are a system triage assistant. You can help engineer with history retrieval and status report on the system.",
    prompt_dir=prompt_dir,
    starting_prompt="""Hello! I'm the System Triage Assistant. I can help you with :
- History Retrieval: Provide important timestamps
- Status Report 
- Asking me any question related to a component of the system.

How can I help you today? 
""",
    args=model_config,
    api=[book_restaurant_yelp],
    knowledge_base=suql_knowledge,
    knowledge_parser=suql_parser,
    model_config=model_config,
).load_from_gsheet(
    gsheet_id="1vrZ4KZuXJbPfYeRvwV8bZUTNzYLtMW7kt3nlxzEtzPc",
)


# Run the conversation loop
asyncio.run(conversation_loop(system_triage_bot, "system_triage_assistant.json"))
