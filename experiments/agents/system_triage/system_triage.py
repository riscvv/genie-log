import asyncio
import os
import random
from uuid import uuid4

import yaml
from suql.agent import postprocess_suql
from suql import suql_execute

from worksheets.agent import Agent
from worksheets.environment import get_genie_fields_from_ws
from worksheets.interface_utils import conversation_loop
from worksheets.knowledge import SUQLKnowledgeBase, SUQLReActParser, SUQLParser

with open("model_config.yaml", "r") as f:
    model_config = yaml.safe_load(f)

# Define your APIs
def status_report(
    system_component: str,
    **kwargs,
):
    table_w_ids = {"log_records": "record_id"}
    database = "postgres"

    print("=" * 80)

    # Get all components
    suql = "SELECT DISTINCT component FROM log_records"
    results, _, _ = suql_execute(suql, table_w_ids, database)
    components = ", ".join([result[0] for result in results])

    # Get component name user refers to
    suql = "SELECT answer('Here are the components in the system: {components}', 'Which component does \"{system_component}\" refers to? Answer with a component name or NONE if it does not refer to any component');".format(
        components=components, system_component=system_component)
    results, _, _ = suql_execute(suql, table_w_ids, database)
    component = results[0][0]
    if component == "NONE" or component not in components:
        return {
            "error":
            "The provided system component {} does not refer to any component in the system."
            .format(system_component)
        }
    print(component)
    print("-" * 80)

    # Retrieve relevant entries
    if "use_is_relevant" in kwargs and kwargs["use_is_relevant"]:
        suql = "SELECT * FROM log_records WHERE component='{component}' OR is_relevant(content, 'What is the current status of {component}?') ORDER BY log_date, log_time DESC LIMIT 5;".format(
            component=component)
    else:
        suql = "SELECT * FROM log_records WHERE component='{component}' OR answer(content, 'Is it related to {component}?') = 'YES' ORDER BY log_date, log_time DESC LIMIT 5;".format(
            component=component)

    print(suql, table_w_ids, database)
    print("-" * 80)
    results, columns, _ = suql_execute(suql, table_w_ids, database)
    query_result_str = ""
    for result in results:
        query_result_str += ", ".join([
            str(col) + ": " + str(res) for (col, res) in zip(columns, result)
        ]) + "\n"
    print(query_result_str)
    query_result_str = query_result_str.replace("\n", ";")
    print("-" * 80)
    # Summarize retrieved data
    suql = "SELECT answer('{}', 'What is the current status of {} given the recent log provided?');".format(
        query_result_str, component)
    results, _, _ = suql_execute(suql, table_w_ids, database)
    print(results)
    print("=" * 80)
    return {"status_summary": results[0]} if results else {}


def history_retrieval(
    system_component: str,
    **kwargs,
):
    # Retrieve relevant entries
    print("=" * 80)
    if "use_is_relevant" in kwargs and kwargs["use_is_relevant"]:
        suql = "SELECT * FROM log_records WHERE is_relevant('What is the current status of {system_component}?') ORDER BY log_date, log_time DESC LIMIT 5;".format(
            system_component=system_component)
    else:
        suql = "SELECT * FROM log_records WHERE answer(content, 'Is it related to {system_component}?') = 'YES' ORDER BY log_date, log_time DESC LIMIT 5;".format(
            system_component=system_component)

    table_w_ids = {"log_records": "record_id"}
    database = "postgres"
    print(suql, table_w_ids, database)
    print("-" * 80)
    results, columns, _ = suql_execute(suql, table_w_ids, database)
    query_result_str = ""
    for result in results:
        query_result_str += ", ".join([
            str(col) + ": " + str(res) for (col, res) in zip(columns, result)
        ]) + "\n"
    query_result_str = query_result_str.replace("\n", ";")
    print(query_result_str)
    print("-" * 80)
    # Summarize retrieved data
    suql = "SELECT answer('{}', 'What is the current status of the system component given the recent log provided?');".format(
        query_result_str)
    print(suql)
    results, _, _ = suql_execute(suql, table_w_ids, database)
    print(results)
    print("=" * 80)
    return {"status_summary": results[0]} if results else {}


# Define path to the prompts

current_dir = os.path.dirname(os.path.realpath(__file__))
prompt_dir = os.path.join(current_dir, "prompts")

# Define Knowledge Base
suql_knowledge = SUQLKnowledgeBase(
    llm_model_name=
    "gpt-4o-mini",  # model name, use this to for _answer, _summary
    tables_with_primary_keys={
        "public.log_records": "record_id",
        "public.log_templates": "event_id"
    },
    database_name="postgres",  # database name
    embedding_server_address=
    "http://127.0.0.1:8501",  # embedding server address for free text
    source_file_mapping={
        "system_triage_general_info.txt":
        os.path.join(current_dir, "system_triage_general_info.txt"
                     )  # mapping of free-text files with the path
    },
    db_host="localhost",  # database host
    db_port="5432",  # database port
    postprocessing_fn=postprocess_suql,  # optional postprocessing function
    result_postprocessing_fn=None,  # optional result postprocessing function
)

# Define Simple LLM Parser
suql_parser = SUQLParser(
    llm_model_name="gpt-4o-mini",
    prompt_selector=
    None,  # optional function that helps in selecting the right prompt
    knowledge=suql_knowledge,
)

# Define the SUQL React Parser
# slower but better for suql query generation, design decision
# suql_react_parser = SUQLReActParser(
#     llm_model_name="gpt-4o-mini",  # model name
#     example_path=os.path.join(current_dir, "examples.txt"),  # path to examples
#     instruction_path=os.path.join(current_dir, "instructions.txt"),  # path to domain-specific instructions
#     table_schema_path=os.path.join(current_dir, "table_schema.txt"),  # path to table schema
#     knowledge=suql_knowledge,  # previously defined knowledge source
# )

# Define the agent
system_triage_bot = Agent(
    botname="System Triage Assistant",
    description=
    "You are a system triage assistant. You can help engineer with history retrieval and status report on the system.",
    prompt_dir=prompt_dir,
    starting_prompt=
    """Hello! I'm the System Triage Assistant. I can help you with:
- Error Triage
- History Retrieval
- Status Report

How can I help you today? 
""",
    args=model_config,
    api=[status_report],
    knowledge_base=suql_knowledge,
    knowledge_parser=suql_parser,
    model_config=model_config,
).load_from_gsheet(gsheet_id="1vrZ4KZuXJbPfYeRvwV8bZUTNzYLtMW7kt3nlxzEtzPc", )

# Run the conversation loop
asyncio.run(
    conversation_loop(system_triage_bot, "system_triage_assistant.json"))
