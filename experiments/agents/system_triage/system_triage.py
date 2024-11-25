import asyncio
import os
from loguru import logger

import yaml
from suql.agent import postprocess_suql
from suql import suql_execute

from worksheets.agent import Agent
from worksheets.interface_utils import conversation_loop
from worksheets.knowledge import SUQLKnowledgeBase, SUQLReActParser, SUQLParser

TABLE_NAME = "log_records_small"
TEMPLATE_NAME = "log_templates_small"
LIMIT = 20

table_w_ids = {TABLE_NAME: "record_id"}
database = "postgres"
important_levels = ["WARNING", "ERROR", "CRITICAL"]
unimportant_levels = ["INFO"]

with open("model_config.yaml", "r") as f:
    model_config = yaml.safe_load(f)


# Helper functions
def get_component_name(system_component: str):
    # Get all components
    suql = "SELECT DISTINCT component FROM {table_name}".format(
        table_name=TABLE_NAME)
    results, _, _ = suql_execute(suql, table_w_ids, database)
    components = ", ".join([result[0] for result in results])

    # Get component name user refers to
    suql = "SELECT answer('Here are the components in the system: {components}', 'Which component does \"{system_component}\" refers to? Answer with a component name or NONE if it does not refer to any component');".format(
        components=components, system_component=system_component)
    results, _, _ = suql_execute(suql, table_w_ids, database)
    component = results[0][0]

    if component == "NONE" or component not in components:
        return None

    return component


def linearize_query_results(results, columns):
    query_result_str = ""
    for result in results:
        query_result_str += ", ".join([
            str(col) + ": " + str(res) for (col, res) in zip(columns, result)
        ]) + "\n"
    logger.info(query_result_str)
    query_result_str = query_result_str.replace("\n", ";")
    logger.info("-" * 80)

    return query_result_str


# Define your APIs
def do_system_status(
    system_component: str,
    **kwargs,
):
    logger.info("=" * 80)

    # Get component
    component = get_component_name(system_component)
    if not component:
        return {
            "error":
            "The provided system component {} does not refer to any component in the system."
            .format(system_component)
        }
    logger.info(component)
    logger.info("-" * 80)

    # Retrieve relevant entries
    if "use_is_relevant" in kwargs and kwargs["use_is_relevant"]:
        suql = "SELECT * FROM {table_name} WHERE component='{component}' OR is_relevant(content, 'What is the current status of {component}?') ORDER BY log_date, log_time DESC LIMIT {limit};".format(
            table_name=TABLE_NAME, component=component, limit=LIMIT)
    else:
        suql = "SELECT * FROM {table_name} WHERE component='{component}' OR answer(content, 'Is it related to {component}?') = 'YES' ORDER BY log_date, log_time DESC LIMIT {limit};".format(
            table_name=TABLE_NAME, component=component, limit=LIMIT)

    logger.info(suql, table_w_ids, database)
    logger.info("-" * 80)
    results, columns, _ = suql_execute(suql, table_w_ids, database)
    query_result_str = linearize_query_results(results, columns)

    # Summarize retrieved data
    suql = "SELECT answer('{}', 'What is the current status of {} given the recent log provided? Provide an appropriate amount of details and reasoning.');".format(
        query_result_str, component)
    results, _, _ = suql_execute(suql, table_w_ids, database)
    logger.info(results)
    logger.info("=" * 80)
    return {"status_summary": results[0]} if results else {}


def do_history_retrieval(
    system_component: str,
    date_start: str,
    date_end: str,
    time_start: str,
    time_end: str,
    metrics: str,
    **kwargs,
):
    # SAMPLE CONVO INPUT:
    # History retrieval
    # I want information about the nova compute manager from 2017-05-14 6AM to 2017-05-14 11:59PM
    # I want to know the duration of the system being abnormal

    logger.info("=" * 80)

    # Get component
    component = get_component_name(system_component)
    if not component:
        return {
            "error":
            "The provided system component {} does not refer to any component in the system."
            .format(system_component)
        }
    logger.info(component)

    levels_str = ", ".join(["'" + level + "'" for level in important_levels])

    logger.info("-" * 80)

    # Retrieve entries within time range
    suql = "SELECT * FROM {table_name} WHERE component='{component}' AND level IN ({levels}) AND log_date BETWEEN '{date_start}' AND '{date_end}' AND log_time BETWEEN '{time_start}' AND '{time_end}' ORDER BY log_date, log_time DESC LIMIT {limit};".format(
        component=component,
        table_name=TABLE_NAME,
        levels=levels_str,
        date_start=date_start,
        date_end=date_end,
        time_start=time_start,
        time_end=time_end,
        limit=LIMIT)

    results, columns, _ = suql_execute(suql, table_w_ids, database)
    # If the amount of logs with important levels are within limit, look at INFO
    if len(results) < LIMIT:
        levels_str = ", ".join(
            ["'" + level + "'" for level in unimportant_levels])
        suql = "SELECT * FROM {table_name} WHERE component='{component}' AND level IN ({levels}) AND log_date BETWEEN '{date_start}' AND '{date_end}' AND log_time BETWEEN '{time_start}' AND '{time_end}' ORDER BY log_date, log_time DESC LIMIT {limit};".format(
            component=component,
            table_name=TABLE_NAME,
            levels=levels_str,
            date_start=date_start,
            date_end=date_end,
            time_start=time_start,
            time_end=time_end,
            limit=LIMIT - len(results))
        results_info, _, _ = suql_execute(suql, table_w_ids, database)
        results.extend(results_info)

    # Not sure if it's necessary, but sort the logs by time
    if "log_time" in columns and "log_date" in columns:
        results.sort(key=lambda x: (
            x[columns.index("log_date")],
            x[columns.index("log_time")],
        ))

    query_result_str = linearize_query_results(results, columns)

    # Summarize retrieved data
    suql = "SELECT answer('{}', 'Given the log provided, provide a summary of the recent history about component {} and provide detailed information on the following aspect in particular: {}');".format(
        query_result_str, component, metrics)
    results, _, _ = suql_execute(suql, table_w_ids, database)
    logger.info(results)
    logger.info("=" * 80)
    return {"history_summary": results[0]} if results else {}


def do_triage_error(system_component: str, **kwargs):
    # Sample convo:
    # - triage error for nova.compute.manager

    logger.info("=" * 80)

    #TODO find the latest 'ERROR' log piece for the component `l1` and summarize it as `l1.summary`
    component_name = get_component_name(system_component)
    # Retrieve last ERROR of the component
    levels_str = ", ".join(["'" + level + "'" for level in important_levels])
    suql_query = f"SELECT * FROM {TABLE_NAME} WHERE component = '{component_name}' AND level IN ({levels_str}) ORDER BY log_date, log_time DESC LIMIT 1;"
    logger.info("Latest `ERROR` log query as {}", suql_query)

    results, columns, _ = suql_execute(
        suql_query,
        table_w_ids,
        database,
    )
    logger.info(results)
    logger.info("+" * 80)
    # TODO: handle no error case
    assert len(results) == 1

    latest_error_log = results[0][columns.index("content")]
    latest_error_log_linearized = linearize_query_results(results, columns)
    logger.info("Latest `ERROR` log piece as {}", latest_error_log)

    # TODO find the most relevant log pieces with the summary of the above log
    # TODO linearize
    if "summary_matching" in kwargs and kwargs["summary_matching"]:
        summary_query = f"SELECT summary('{latest_error_log}');"
        # TODO find summary structure to find the actual summarized content
        summary, _, _ = suql_execute(summary_query, table_w_ids, database)
        summary = summary[0]
    else:
        # Default to using content directly
        summary = latest_error_log

    logger.info("content summary as {}", summary)

    if "use_is_relevant" in kwargs and kwargs["use_is_relevant"]:
        relevant_query = f"is_relevant(content, '{summary}')"
    else:
        relevant_query = f"answer(content, 'Is it related to {summary}?') = 'YES'"

    important_levels_str = ", ".join(
        ["'" + level + "'" for level in important_levels])
    unimportant_levels_str = ", ".join(
        ["'" + level + "'" for level in unimportant_levels])
    # Retrieve import entries within relevance check
    suql = f"SELECT * FROM {TABLE_NAME} WHERE level IN ({important_levels_str}) AND {relevant_query} ORDER BY log_date, log_time DESC LIMIT {LIMIT};"
    results, columns, _ = suql_execute(suql, table_w_ids, database)
    # If the amount of logs with important levels are within limit, look at INFO
    if len(results) < LIMIT:
        suql = f"SELECT * FROM {TABLE_NAME} WHERE level IN ({unimportant_levels_str}) AND {relevant_query} ORDER BY log_date, log_time DESC LIMIT {LIMIT - len(results)};"
        normal_results, _, _ = suql_execute(suql, table_w_ids, database)
        results.extend(normal_results)

    logger.info("10 most relevant log piece as {}", results)
    #TODO provide insights sorted by relevancy
    query_result_str = linearize_query_results(results, columns)

    # Summarize retrieved data
    suql = "SELECT answer('{}', 'Given the recent log provided, analyze the cause of the following event: {}. Provide an appropriate amount of details and reasoning. Cite specific lines of log to support your analysis.');".format(
        query_result_str, latest_error_log_linearized)
    results, _, _ = suql_execute(suql, table_w_ids, database)
    logger.info(results)
    logger.info("=" * 80)

    return {"triage_error_result": results[0]} if results else {}


# Define path to the prompts

current_dir = os.path.dirname(os.path.realpath(__file__))
prompt_dir = os.path.join(current_dir, "prompts")

# Define Knowledge Base
suql_knowledge = SUQLKnowledgeBase(
    llm_model_name=
    "gpt-4o-mini",  # model name, use this to for _answer, _summary
    tables_with_primary_keys={
        "public.{table_name}".format(table_name=TABLE_NAME): "record_id",
        "public.{template_name}".format(template_name=TEMPLATE_NAME):
        "event_id"
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
    """Hello! I'm the System Triage Assistant. I can help you with :
- Triage Error
- History Retrieval
- System Status

How can I help you today? 
""",
    args=model_config,
    api=[do_system_status, do_history_retrieval, do_triage_error],
    knowledge_base=suql_knowledge,
    knowledge_parser=suql_parser,
    model_config=model_config,
).load_from_gsheet(gsheet_id="1vrZ4KZuXJbPfYeRvwV8bZUTNzYLtMW7kt3nlxzEtzPc", )

# Run the conversation loop
asyncio.run(
    conversation_loop(system_triage_bot, "system_triage_assistant.json"))
