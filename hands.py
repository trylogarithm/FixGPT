import asyncio
import os
import sys
import traceback
from typing import List
import datetime
import json
from langchain_openai import ChatOpenAI
from agents import Agent, Runner
from agents.run import RunConfig
from tools import initialize_default_tools, tool_registry, get_available_tools
from brain import plan_next_step, get_tool_metadata
from config_loader import get_config
from hands_prompt import HANDS_INSTRUCTIONS
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration will be loaded from YAML

def check_openai_config():
    """Ensure OpenAI API key is configured."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is required. "
            "Please set it in your environment or .env file."
        )
    return api_key


def create_agent_tool_wrapper(tool_id: str, registry):
    """Create a wrapper that makes our modular tools compatible with the agents framework."""
    from agents import function_tool
    from tools.base_tool import ToolResult
    from typing import Optional
    
    # Get the tool metadata
    tool = registry.get_tool(tool_id)
    if not tool:
        raise ValueError(f"Tool {tool_id} not found in registry")
    
    metadata = tool.metadata
    
    # Create a simple function for Prometheus tools (most common case)
    if tool_id == "prometheus_query":
        async def prometheus_query_function(
            query: str,
            query_type: Optional[str] = "instant", 
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            step: Optional[str] = "15s",
            timeout: Optional[str] = None
        ):
            """Query metrics from Prometheus using PromQL. Supports instant and range queries."""
            kwargs = {k: v for k, v in locals().items() if v is not None and k != 'kwargs'}
            try:
                result = await registry.execute_tool(tool_id, kwargs)
                if result.success:
                    return result.data
                else:
                    return {"error": result.error_message}
            except Exception as e:
                return {"error": str(e)}
    
        return function_tool(
            prometheus_query_function,
            name_override="prometheus_query",  # Valid OpenAI function name
            strict_mode=False  # Disable strict mode to avoid additionalProperties issues
        )
    
    # For other tools, create specific wrappers based on tool type
    if tool_id == "k8s_service_health":
        async def k8s_service_health_function(
            service_name: str,
            namespace: Optional[str] = "default"
        ):
            """Check health and status of Kubernetes services including pods, deployments, and events."""
            kwargs = {k: v for k, v in locals().items() if v is not None}
            try:
                result = await registry.execute_tool(tool_id, kwargs)
                if result.success:
                    return result.data
                else:
                    return {"error": result.error_message}
            except Exception as e:
                return {"error": str(e)}

        return function_tool(
            k8s_service_health_function,
            name_override="k8s_service_health",
            strict_mode=False
        )
    
    elif tool_id == "kubectl_command":
        async def kubectl_command_function(
            command: str,
            namespace: Optional[str] = "default",
            output_format: Optional[str] = "text",
            additional_flags: Optional[str] = ""
        ):
            """Execute kubectl commands directly for deep cluster inspection."""
            kwargs = {k: v for k, v in locals().items() if v is not None}
            try:
                result = await registry.execute_tool(tool_id, kwargs)
                if result.success:
                    return result.data
                else:
                    return {"error": result.error_message}
            except Exception as e:
                return {"error": str(e)}

        return function_tool(
            kubectl_command_function,
            name_override="kubectl_command",
            strict_mode=False
        )
    
    elif tool_id == "kubectl_events":
        async def kubectl_events_function(
            namespace: Optional[str] = "default",
            event_type: Optional[str] = "all",
            reason_filter: Optional[str] = None,
            time_window_minutes: Optional[int] = 60,
            limit: Optional[int] = 50
        ):
            """Analyze Kubernetes events with filtering for critical issues."""
            kwargs = {k: v for k, v in locals().items() if v is not None}
            try:
                result = await registry.execute_tool(tool_id, kwargs)
                if result.success:
                    return result.data
                else:
                    return {"error": result.error_message}
            except Exception as e:
                return {"error": str(e)}

        return function_tool(
            kubectl_events_function,
            name_override="kubectl_events",
            strict_mode=False
        )
    
    elif tool_id == "service_connectivity":
        async def service_connectivity_function(
            service_name: str,
            namespace: Optional[str] = "default",
            port: Optional[int] = 8080,
            protocol: Optional[str] = "http",
            health_path: Optional[str] = "/health",
            timeout_seconds: Optional[int] = 30
        ):
            """Test actual service connectivity and functionality."""
            kwargs = {k: v for k, v in locals().items() if v is not None}
            try:
                result = await registry.execute_tool(tool_id, kwargs)
                if result.success:
                    return result.data
                else:
                    return {"error": result.error_message}
            except Exception as e:
                return {"error": str(e)}

        return function_tool(
            service_connectivity_function,
            name_override="service_connectivity",
            strict_mode=False
        )
    
    elif tool_id == "k8s_logs":
        async def k8s_logs_function(
            service_name: str,
            namespace: Optional[str] = "default",
            time_window_minutes: Optional[int] = 60,
            log_level: Optional[str] = None,
            limit: Optional[int] = 100,
            follow: Optional[bool] = False
        ):
            """Query logs from Kubernetes services using kubectl."""
            kwargs = {k: v for k, v in locals().items() if v is not None}
            try:
                result = await registry.execute_tool(tool_id, kwargs)
                if result.success:
                    return result.data
                else:
                    return {"error": result.error_message}
            except Exception as e:
                return {"error": str(e)}

        return function_tool(
            k8s_logs_function,
            name_override="k8s_logs",
            strict_mode=False
        )
    
    elif tool_id == "prometheus_alerts":
        async def prometheus_alerts_function(
            source: Optional[str] = "prometheus",
            state: Optional[str] = None,
            filter: Optional[str] = None
        ):
            """Query active alerts from Prometheus and Alertmanager."""
            kwargs = {k: v for k, v in locals().items() if v is not None}
            try:
                result = await registry.execute_tool(tool_id, kwargs)
                if result.success:
                    return result.data
                else:
                    return {"error": result.error_message}
            except Exception as e:
                return {"error": str(e)}

        return function_tool(
            prometheus_alerts_function,
            name_override="prometheus_alerts", 
            strict_mode=False
        )
    
    elif tool_id == "prometheus_targets":
        async def prometheus_targets_function(
            state: Optional[str] = "active"
        ):
            """Check status of Prometheus targets and service discovery."""
            kwargs = {k: v for k, v in locals().items() if v is not None}
            try:
                result = await registry.execute_tool(tool_id, kwargs)
                if result.success:
                    return result.data
                else:
                    return {"error": result.error_message}
            except Exception as e:
                return {"error": str(e)}

        return function_tool(
            prometheus_targets_function,
            name_override="prometheus_targets",
            strict_mode=False
        )

    # Fallback for any remaining tools
    async def generic_tool_function():
        """Execute the tool with the given inputs."""
        try:
            result = await registry.execute_tool(tool_id, {})
            if result.success:
                return result.data
            else:
                return {"error": result.error_message}
        except Exception as e:
            return {"error": str(e)}
    
    # Set function metadata
    generic_tool_function.__name__ = metadata.id
    generic_tool_function.__doc__ = metadata.description
    
    return function_tool(
        generic_tool_function,
        name_override=metadata.id,  # Use id instead of name (no spaces)
        description_override=metadata.description,
        strict_mode=False  # Disable strict mode
    )


def save_conversation_turn_to_json(role: str, content: str, output_dir: str):
    """Saves a conversation turn by appending to a single JSON log file for the run."""
    if not output_dir or not os.path.exists(output_dir):
        logger.error(f"Error: Output directory '{output_dir}' not set or does not exist. Cannot save message.")
        return
    
    log_file_path = os.path.join(output_dir, "conversation_log.json")
    timestamp = datetime.datetime.now().isoformat()
    new_turn = {
        "timestamp": timestamp,
        "role": role,
        "content": content,
    }
    
    log_entries = []
    try:
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r') as f:
                try:
                    log_entries = json.load(f)
                    if not isinstance(log_entries, list):
                        logger.warning(f"Warning: Existing log file {log_file_path} does not contain a list. Re-initializing.")
                        log_entries = []
                except json.JSONDecodeError:
                    logger.warning(f"Warning: Existing log file {log_file_path} is not valid JSON. Re-initializing.")
                    log_entries = []
        
        log_entries.append(new_turn)
        
        with open(log_file_path, 'w') as f:
            json.dump(log_entries, f, indent=4)
        
        logger.info(f"Appended conversation turn to {log_file_path}")
    except Exception as e:
        logger.error(f"Error saving conversation turn to {log_file_path}: {e}")


def llm():
    return ChatOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        model="gpt-4o-mini",
        temperature=0.1
    )


def get_default_run_config() -> RunConfig:
    """Get default RunConfig without MCP."""
    from openai import AsyncOpenAI
    from agents import OpenAIChatCompletionsModel
    
    api_key = os.environ.get("OPENAI_API_KEY")
    model_name = "gpt-4o-mini"
    
    client = AsyncOpenAI(api_key=api_key)
    
    model = OpenAIChatCompletionsModel(
        model=model_name,
        openai_client=client,
    )
    
    config = RunConfig(
        model=model,
        model_provider=client,
    )
    
    return config


async def _initialize_resources() -> tuple[RunConfig, list]:
    """Initializes RunConfig and sets up modular tools from YAML configuration."""
    logger.info("Initializing Config and Tools")
    
    # Load configuration from YAML
    config_loader = get_config()
    logger.info(f"Using configuration: {config_loader}")
    
    # Setup logging level from config
    log_level = config_loader.get_log_level()
    logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    run_config = get_default_run_config()
    
    # Initialize the tool registry with enabled tools from YAML config
    registry = initialize_default_tools(config_loader)
    
    # Convert tools to the format expected by the agents framework
    tools = []
    for tool_metadata in registry.list_tools():
        # Create tool wrapper for agents framework
        tool_wrapper = create_agent_tool_wrapper(tool_metadata.id, registry)
        tools.append(tool_wrapper)
    
    enabled_tools = [t.metadata.name for t in registry._tools.values()]
    logger.info(f"Initialized {len(tools)} tools from YAML config: {enabled_tools}")
    
    # CRITICAL: Prevent hallucination - stop if no tools available
    if len(tools) == 0:
        raise RuntimeError("CRITICAL: No tools available! Cannot run investigation. Check tool configuration and connectivity.")
    
    return run_config, tools


async def summarise_output(history: List[dict[str, any]], plan: List[dict[str, any]], user_goal: str):
    """Summarises the output of the debugging investigation."""
    prompt = f"""
    You are summarizing a production debugging investigation. Create a structured report of the findings.
    
    STRUCTURED OUTPUT SCHEMA:
    You MUST use the following JSON schema:
    ```json
    {{
        "investigation_metadata": {{
            "incident_id": "string",
            "timestamp": "ISO-8601 datetime",
            "initial_query": "string",
            "affected_services": ["string"]
        }},
        "overall_assessment": {{
            "summary": "string",
            "severity": "critical|high|medium|low",
            "status": "resolved|ongoing|escalated",
            "root_cause_identified": true|false
        }},
        "investigation_path": [
            {{
                "step_number": 1,
                "action": "string",
                "rationale": "string",
                "tool_used": "string",
                "key_findings": "string"
            }}
        ],
        "key_findings": [
            {{
                "id": 1,
                "title": "string",
                "evidence": ["string"],
                "impact": "string",
                "affected_services": ["string"]
            }}
        ],
        "root_cause_analysis": {{
            "identified_root_cause": "string",
            "confidence": "high|medium|low",
            "supporting_evidence": ["string"],
            "timeline": "string"
        }},
        "recommended_actions": [
            {{
                "id": 1,
                "action": "string",
                "priority": "immediate|high|medium|low",
                "expected_impact": "string",
                "owner": "string"
            }}
        ],
        "metrics_summary": {{
            "error_rate_change": "string",
            "latency_impact": "string",
            "affected_endpoints": ["string"],
            "time_to_detection": "string",
            "time_to_resolution": "string"
        }}
    }}
    ```

    History: {json.dumps(history, indent=2)}
    User Goal: {user_goal}
    Plan: {json.dumps(plan, indent=2)}

    Create a concise but comprehensive summary focusing on actionable insights.
    """

    llm_response = await llm().ainvoke(prompt)
    return llm_response.content


async def run_hands_plan(user_goal: str):
    """Run the debugging plan using reactive planning approach."""
    # Load configuration
    config_loader = get_config()
    max_steps = config_loader.get_max_steps()
    output_directory = config_loader.get_output_directory()
    
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir_for_run = os.path.join(output_directory, run_id)
    os.makedirs(output_dir_for_run, exist_ok=True)
    output_file_path = os.path.join(output_dir_for_run, "hands_output.txt")

    logger.info("---- Starting Hands Agent (Production Debugging Mode) ----")
    
    try:
        config, tools = await _initialize_resources()
        
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        tomorrow = now + datetime.timedelta(days=1)
        
        formatted_instructions = HANDS_INSTRUCTIONS.format(
            current_datetime=now.strftime('%Y-%m-%d %H:%M:%S'),
            current_day_name=now.strftime("%A"),
            current_date=now.strftime('%Y-%m-%d'),
            yesterday_date=yesterday.strftime('%Y-%m-%d'),
            tomorrow_date=tomorrow.strftime('%Y-%m-%d')
        )
        
        hands_agent = Agent(
            name="Hands",
            instructions=formatted_instructions,
            tools=tools
        )
        
        # Get tool metadata for the brain
        tool_metadata = get_tool_metadata()
        
        history = []
        step_count = 0
        whole_plan = []
        
        with open(output_file_path, "a") as output_file:
            while True:
                # Check if we've reached the maximum number of steps
                if step_count >= max_steps:
                    logger.info(f"Reached maximum number of steps ({max_steps}). Stopping investigation.")
                    break
                
                current_step = await plan_next_step(user_goal, tool_metadata, history)
                
                if current_step == "PLAN COMPLETE":
                    logger.info("Brain returned PLAN COMPLETE. Stopping.")
                    break
                
                step_count += 1
                logger.info(f"Executing step {step_count}/{max_steps}: {current_step}")
                
                # Build the conversation for this step
                conversation = [
                    {"role": "system", "content": hands_agent.instructions},
                    {"role": "user", "content": f"User goal: {user_goal}"},
                    {"role": "user", "content": f"Current step: {json.dumps(current_step, indent=2)}"},
                    {"role": "user", "content": f"History: {json.dumps(history, indent=2)}"},
                ]
                
                result = await Runner.run(
                    starting_agent=hands_agent,
                    input=conversation,
                    run_config=config
                )
                
                output = result.final_output
                logger.info(f"Step {step_count} output: {output}")
                history.append({"step": current_step, "output": output})
                whole_plan.append(current_step)
                
                # Save to output file
                output_file.write(f"Step {step_count}:\n")
                output_file.write(f"Plan Step: {json.dumps(current_step, indent=2)}\n")
                output_file.write(f"Output: {json.dumps(output, indent=2) if not isinstance(output, str) else output}\n")
                output_file.write("="*40 + "\n")
        
        logger.info("Reactive plan complete.")
        
        # Generate summary
        summary = await summarise_output(history, whole_plan, user_goal)
        
        # Save summary
        summary_path = os.path.join(output_dir_for_run, "investigation_summary.json")
        with open(summary_path, 'w') as f:
            f.write(summary)
        
        return summary 
                
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        logger.error(traceback.format_exc())
        raise
    finally:
        logger.info("Hands Agent execution complete.")